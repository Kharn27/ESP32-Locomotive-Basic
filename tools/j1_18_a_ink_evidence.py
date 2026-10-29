#!/usr/bin/env python3
"""J1.18-A CPC6128 INK oracle, no C99/firmware implementation.

The Caprice32 processes are genuinely independent; SNA files are transient.
Permanent SHA pins are added outside the archive AFTER the first CPC acquisition.
Unsealed archives and static-ROM predictions never become CPC_ORACLE_VERIFIED.
"""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests/oracles'))
import token_ram_oracle as cpc
from signed_print_oracle import parse_integer

PHASE = 'J1.18-A'
SOURCES = ROOT / 'tests/oracles/inputs/j1_18_a'
CASES = {
    'I00': '0,0', 'I126': '1,26', 'I106': '1,6',
    'I206': '2,6', 'I318': '3,18', 'I1526': '15,26',
    'I127': '1,27', 'I131': '1,31', 'I1266': '1,26,6',
    'I1626': '16,26', 'IN126': '-1,26',
    'I132': '1,32', 'I1N1': '1,-1'
}
SESSIONS = ('original', 'repeat')
LINES = [10, 20, 30, 40]
GHCR = 'ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c'
# I00 starts on red ink-0 so its black-background change is observable.
# All other cases begin black background, white foreground, MODE 1.
def setup(case):
    return ['MODE 1', 'INK 0,' + ('6' if case == 'I00' else '0'),
            'INK 1,26', 'INK 2,6', 'INK 3,18',
            'PAPER 0', 'PEN 1', 'CLS', 'NEW']
# Caprice screenshot filenames are wall-clock-second based. Space the two
# within-process captures by enough real execution time to prevent overwrite.
CHRONO_DELAY = ' '.join(['CAP32_DELAY'] * 96)
CHRONO = ['MODE 1', 'INK 0,0', 'INK 1,26', 'INK 2,6', 'INK 3,18',
          'PAPER 0', 'PEN 1', 'CLS', 'NEW']
# Extract independently from the FIRST authentic GitHub acquisition and pin
# its actual archive byte hashes here. Never derive these from manifest.json.
# Historic J1.17-A pins are *not* INK evidence. INK SHA are separate.
# Immutable pins captured from *actual Caprice32 Actions SHA256 outputs*:
# https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974044447
# Acquisition commit 0d4214fdc4670dcdaa36f7704fe692b92d43d963,
# its parent 6e9b17b8d545a57ef3942f217c9b4d3daeae8c38.
# Independently checked against the 243-file ZIP Actions artifact 12941622604.
SEALED = {
    "original/chronology/caprice.log": "ba77fa282ec4f481a4f38e58a9d06e6ac5097419b97680cbc0b47dee0c2d8041",
    "original/chronology/capture.json": "8d1910fef9bc20e0bd50f7e96368f6da198d73393f22d1c1ab1cb2565e0de58f",
    "original/chronology/screen_0.png": "55232838c572858e6af8d2e98783863756db61d2c2c7c36381337f6d6464de93",
    "original/chronology/screen_1.png": "7293430e001993672dccf358d1bd61bc9e4bfea76b9e74ed0fc613c3e6a11097",
    "original/I00/baseline/caprice.log": "35930c64469c507de985075191ee133322f71803a543368eba7bcf179c4aa272",
    "original/I00/baseline/screen.png": "4ca1a83879978a4e682b039b418168382cb5e8cec3f149a63d1c786650ba8a0f",
    "original/I00/capture.json": "f5c2f7fe6018abb2a68fbde731a4a7489151a2c048d6812a2f6fe23cf084147a",
    "original/I00/list/caprice.log": "a5d178dd4393a054efbd8442a58e165d528f6cfb87e1d186ae946cebd9574f5c",
    "original/I00/list/screen.png": "9904dec17dca441aba5c26edb75b40e0977a9bee973ef303ab573f2145b4c1d6",
    "original/I00/program.bin": "5c28723541029bc2c54a7f368f6b7c70d34626ec11f6c0293462742b24dfc787",
    "original/I00/run/caprice.log": "0e657fc0a0c2938d970ed63ccfc753da5f95870d6fa00df144969fc997c325b9",
    "original/I00/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/I00/run/screen.png": "019539c14210f1f87a795f9d5965540b3818e7e7dc848aa9fc5908f27166b897",
    "original/I106/baseline/caprice.log": "5c07ee9580194c726ae9ba0c02cb9b7ffa0a8eadc8feac14b065d3903e55459f",
    "original/I106/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I106/capture.json": "f01ba3d5ff68ebd0cfeee47df448e1ee243b5eedcb8686f4dc3369d8ca5f2594",
    "original/I106/list/caprice.log": "55b04d910f4f745eb297e743d3275bb23fbbcfd62a69504dbbba55cd324ee14c",
    "original/I106/list/screen.png": "580643965a0966cf048cacc998537461de61aff3fb90aecb74ca972717ef75a7",
    "original/I106/program.bin": "6dd48201aa25587c14f1addcad6a1dd11f93ba2c0dc0afe6023344188ebf2ada",
    "original/I106/run/caprice.log": "665d4f27c284de2e1b3d34237c98f9324a02cb48ba5432a8988077d9a9bc4a2e",
    "original/I106/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/I106/run/screen.png": "04a4ca66fe03d809b9b054af6f4562a39768e7723c2469b08d57d64cc90ef66f",
    "original/I126/baseline/caprice.log": "1d05e7a6344ae1ecde6172c7b36f59a69b59e2aace1d28368d6c31617a8ca733",
    "original/I126/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I126/capture.json": "2ce19b9a9582850e0977fe8e54e35eae83bf97bae9f47392839fd1fafe723f19",
    "original/I126/list/caprice.log": "64ea9959186bf8a2067c1214922c30a2e604035dfe86fbcc9cf4c556e5460fe5",
    "original/I126/list/screen.png": "40f4a2e266fa938c883ca68ac0dca14f0bcc66b43d310008c90238c268ef600a",
    "original/I126/program.bin": "ee4a9d3a0abb0f8d9710fb44ab47a3dc2c1f45fef4eeb34e96e0afd4661285de",
    "original/I126/run/caprice.log": "ea9575f9a82f04264424e978f7e4e456aa317ca1472320f461e55f949726e5c3",
    "original/I126/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/I126/run/screen.png": "bb71f207ed86c9cad2ccbb80daf950ea9a02c48d76b902eed0bca77a49aae84b",
    "original/I1266/baseline/caprice.log": "79f89ab6a982f6e6594f7ed9f01e66c2a156aa7d38a2724de006db457535cdde",
    "original/I1266/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I1266/capture.json": "bcf80d6f1c562919a327d81b04a948b1e7ecff74a9b577e9af93b640b083a18d",
    "original/I1266/list/caprice.log": "5c36c87421e2e863295602b8434ab3adddeb0d05d2d7fdeeb9f4862b1a374e15",
    "original/I1266/list/screen.png": "1e443c7b9c6ea87028b5accca5ef8e3227c402ad3bfa7fcb8d34a5f1d6e80def",
    "original/I1266/program.bin": "627786c3816da29da184b7fa417b11c4608bf436a3909476ad3929f4df2c9c19",
    "original/I1266/run/caprice.log": "9249c725f40c5f84b5bc8e8f4812cb7cfa889a386c1d62edc600f6252756981d",
    "original/I1266/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/I1266/run/screen.png": "af22bd563ed9169137aef505ba5a87888fc6ce927a131d324e20ac0b4541cd17",
    "original/I127/baseline/caprice.log": "1207a21f4d0d38212fb8c69f9afae05f1b60db87c6405877c0ad2fbedf3f79b5",
    "original/I127/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I127/capture.json": "1fc53526d9dbe1f28e87f668e9adfb5352352b003378bb51fd630f50665e5723",
    "original/I127/list/caprice.log": "e2cf9ccd291133f8d3ba5434d249070d471b439aead41a3fc3c9090102b3bb75",
    "original/I127/list/screen.png": "3606b742868189032af76841388d27a2cf16c73679df0033c15b12d7f45ab2a8",
    "original/I127/program.bin": "51bd26d73201fb3db2cb374c7ee0b7bed0b6fe7febb99cddcce13de5f3b22663",
    "original/I127/run/caprice.log": "0e6dd17a8dc9dd409d7bb7b5596ac4aef31df361c925b202aef7139e548883c2",
    "original/I127/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/I127/run/screen.png": "46a60fa17dc7e985cb8e30fbe6d6eede3440f626eb4635786b8b3a4a85409ad8",
    "original/I131/baseline/caprice.log": "4125c66fdc673926ea394c03a852c4ffe61c2940f56a6314f32feda1040e19cb",
    "original/I131/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I131/capture.json": "8130fef93db36dc5e4cd5ab308180136c5a5944a42b31de1c8cfa3353a8afb3b",
    "original/I131/list/caprice.log": "1e7ba72470effa7552beda5297d3b9bd4e604bb487f36cf9fd62813003ee3c51",
    "original/I131/list/screen.png": "3a8ee093af4b28bab9025bfabab96b40652e9ce51d12ab5743057c7afede2203",
    "original/I131/program.bin": "95178820a8495d227b9ceec800d79ed1653a1b65a85459f3ec62759220a8d280",
    "original/I131/run/caprice.log": "56566d4f3376151d6d7cfd938e659b9385b88e94e7aa1cb503f57906e96e804e",
    "original/I131/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/I131/run/screen.png": "3d861d78186a0e38232219df8e6320bddee0d38be78d8c1770df6ade7ca52a79",
    "original/I132/baseline/caprice.log": "b882c95779a91ed3cf3d1ad8fcea3dbd0afe569b66d35e465fbe674bd6d0411a",
    "original/I132/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I132/capture.json": "13be691862e79e4947751e1e74bbedc706128ee3161c152dbafdcb33ff2ac98e",
    "original/I132/list/caprice.log": "5a287151d8e5cdb0a7b2ca1b83bae5aebdd2d969ebe391119ef6d730d7b3f1a8",
    "original/I132/list/screen.png": "30c7d76c850a670eb39a8bb4183cfc2a2d83fe636964c5c2973f66b475d0490f",
    "original/I132/program.bin": "0473ba5c77155018186282b14cf6688c47aae05f639fb8cb44f72c1dd6213895",
    "original/I132/run/caprice.log": "48aee182237a1ef4601c1a65185d73b740a5b097907349775c0fab52188b1911",
    "original/I132/run/printer.dat": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
    "original/I132/run/screen.png": "f778cc7b8d3d8895ed78ba8f28c02e71ae8956e184581fcafd233b9d3fc0c9f4",
    "original/I1526/baseline/caprice.log": "bd763bc8f7475b8a6924dc24a5427b5a55e895676d3868cec478768d76e21cde",
    "original/I1526/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I1526/capture.json": "a27d31120fccf907276513938b9b03d378154faec05e5b1a036b7c2eeb866a18",
    "original/I1526/list/caprice.log": "11c06bc835bcf54e904beb8f6da11c5da27e176805f0c647824f06e88e32ffd9",
    "original/I1526/list/screen.png": "135c7552dbb9c3eb25a9bf20980154ebf85c4628b7bec26a29e0caf257502c50",
    "original/I1526/program.bin": "8ff894ca9285ba1099edc38251050f7e743f82cab90c955af460134c0c43054b",
    "original/I1526/run/caprice.log": "755417643a6a9915c7964858c97d6e04f97c641fdfab3ca753a13bb35e367ee4",
    "original/I1526/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/I1526/run/screen.png": "15cd1af91a1d939ca91d9cdb3f4871866058d944c04dcad41331022d05ef4c73",
    "original/I1626/baseline/caprice.log": "80e311e7eaaf2b0cba7b0cdcd8f09c6809d3d8f852ce207505f12a9031f0febd",
    "original/I1626/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I1626/capture.json": "122f24f8571825d6ffecd667c674a13d4fb8de7b4593ccd5523b3bc9727ef1db",
    "original/I1626/list/caprice.log": "9c124de2d1d08e6dc7450d8e68f9b9681b14ba160d94d5e36ed3c002fe868bd0",
    "original/I1626/list/screen.png": "0467757653d49b84044fa7cf07a0fe68529eeb9480770c2b23fc1b0936b07a72",
    "original/I1626/program.bin": "d62a66f084b65cf5f2a21330d23939f845776f2302a822a0da95a1fd9fffed24",
    "original/I1626/run/caprice.log": "37476468bd4be734331f74300e51720e16859abeddeda70f0d4935ea823096f1",
    "original/I1626/run/printer.dat": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
    "original/I1626/run/screen.png": "731c95b4a6ab7e0b82b18def3a9abad5556b7511142cce8d7e9782aa9dbfebb1",
    "original/I1N1/baseline/caprice.log": "7e413043ad51371b6eadb235582f932fde65d9e88e6e2799b37b0f48de4211a0",
    "original/I1N1/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I1N1/capture.json": "396f09e5dec2da8d4cb4b69254721362fbbd63666b7ae3f93e86ac1fd96a9a74",
    "original/I1N1/list/caprice.log": "d6121572b1bb06033d316cdea490753ddbacf496892058aacf36558f30880ff9",
    "original/I1N1/list/screen.png": "0246583f9d0334efa73e59cb90ab92fc8bead3a0b98a63a781b46ae9fa2e36a4",
    "original/I1N1/program.bin": "039c57c82cd44d22367dfed410ee6d4c0da30e81cf378e35f14fa0c1f3fd3bfa",
    "original/I1N1/run/caprice.log": "b1f0a6b06c5ae212fa919b8f74a8bb91d1cb3e8297e952185b8980dd7fe843cc",
    "original/I1N1/run/printer.dat": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
    "original/I1N1/run/screen.png": "19d526e97c1a784b575c5ae932ccd661ef70208828e7df297887785342ad3fbf",
    "original/I206/baseline/caprice.log": "35ae1ebe43eaaf9653906d44b77ed0340b8d0ea53e825658f068fff11a4563f4",
    "original/I206/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I206/capture.json": "f89809d1b3ffe7693ca7adb03c77c94c5786d905ed4f69a0c8d393da08c3220a",
    "original/I206/list/caprice.log": "6ecd45e2dca3e5842026911129fb0ce21ffdb4163815a2e96b56ffe8ecb61779",
    "original/I206/list/screen.png": "04ee6b29ad675eb9e278df66ea4007731860d8b2318be176638929b793d27da0",
    "original/I206/program.bin": "ef310cd0f3523059ccef31114b1e54a9dee1cc3c4a6d23ca058ff22e20043ba3",
    "original/I206/run/caprice.log": "faf0ab6ea5093439b26a3e340e572cc79a95be3fa5272fb5ddab10e065523817",
    "original/I206/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/I206/run/screen.png": "b1a3c14f37b46d8073032fd8644cc303f36c02258c8a34d3081b73aba0dd5cc8",
    "original/I318/baseline/caprice.log": "4193a03815fe484fe8b36ce635e79886b2fd818713a8232be5c34cd03fd4fa86",
    "original/I318/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/I318/capture.json": "d609f3330a2d07753f0465c0931f045af60e80fe2f4d22b69e0af4b61ee346d5",
    "original/I318/list/caprice.log": "c39cab8b1543b6c0963640257c06326b614f3d4b1fd5e3fb9f7e1b9ba6cc0271",
    "original/I318/list/screen.png": "86c21137c10814082b11757a8acb1513a8b436d9bc963d875c964276b4f5a95c",
    "original/I318/program.bin": "610fff221ad4726b45d6ed1a244da209954f1fdbb6910173afa5e43ecc994c6d",
    "original/I318/run/caprice.log": "a4b26724eb291072352219d5927ba04885982067b01d1dd5bf9b3d1ca21fb60e",
    "original/I318/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/I318/run/screen.png": "258cf108a76ddf41b6d8e83e814a50fc0b2b009f6bbacac225220aacb43266a2",
    "original/IN126/baseline/caprice.log": "dbf98da6faa2a0f40037b5986196b77bebff76d0f12f0677089923ae5c2d5a40",
    "original/IN126/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "original/IN126/capture.json": "73a48207990119563f3e75cbdf83eb109ec1f571e8ce538c1eb0f3a87a4c5999",
    "original/IN126/list/caprice.log": "13c217a795c27e8698dd3e97259c744725e3872ce6fd6fd42341915d1d0d577a",
    "original/IN126/list/screen.png": "3c9bd5647054183e11b57d7b6f0c36ead56e1e7d579d95f9cd706075f484d5fd",
    "original/IN126/program.bin": "234fe829bd9c1774d88a4505050368fbcdff629b0b8eae483d18128c921f51e7",
    "original/IN126/run/caprice.log": "cae312a23ea5678e28c0b3eb435cac67ae3317573596e569273f8445fe8d5f14",
    "original/IN126/run/printer.dat": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
    "original/IN126/run/screen.png": "82879bfb61cb3129099e21620d952dfe063001469a91b754ee01c130727c7ef3",
    "repeat/chronology/caprice.log": "8a873211d97a3bd81df379e74146d1f71ef87d0572dcc912e01f984c8c18aca8",
    "repeat/chronology/capture.json": "91d5610dee67757c3733a91ebd57ffcc838c9bfb4c5a09e0fa85c227de3aae2b",
    "repeat/chronology/screen_0.png": "55232838c572858e6af8d2e98783863756db61d2c2c7c36381337f6d6464de93",
    "repeat/chronology/screen_1.png": "7cf5e29b17b775383e540903b6501207868dc2600998cc0fdaf8af2ff71146a3",
    "repeat/I00/baseline/caprice.log": "a6de848f97cad9e52a981ecc863990e1024b8737d1d74ff1bce7acba2a162d98",
    "repeat/I00/baseline/screen.png": "4ca1a83879978a4e682b039b418168382cb5e8cec3f149a63d1c786650ba8a0f",
    "repeat/I00/capture.json": "e7629f4492cf58c7f56d6ba7762aa963d780bab12828c22e7888715631efa99f",
    "repeat/I00/list/caprice.log": "41f608872e7df7ff6768ed767f9aae9813cededc7f3d76a3739f0d04af12a7d9",
    "repeat/I00/list/screen.png": "cb87475ea8ee71b853a8c1348659410fb8703f76eab4bcf9785da37790db90b2",
    "repeat/I00/program.bin": "5c28723541029bc2c54a7f368f6b7c70d34626ec11f6c0293462742b24dfc787",
    "repeat/I00/run/caprice.log": "ee084a97927a59ce2f10eb475aeafd58ff53860995f84133979b4720d50925b0",
    "repeat/I00/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/I00/run/screen.png": "08eec1971e954e2afab57767516a306b1acfd43c084ff620859950cbef557430",
    "repeat/I106/baseline/caprice.log": "eb98d5677ff8d4af2cf5302ebc9aa61a8b666cf4936931fe82cbbb51ffe19a38",
    "repeat/I106/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I106/capture.json": "c029a7ea2969504cc9e532f0efba00baf98193c1a3fc9498909bfa9f2e69633b",
    "repeat/I106/list/caprice.log": "4506a8952a058d46037ff6cd2b11ceef62a50eee25f4e0ca3e6f161870063edb",
    "repeat/I106/list/screen.png": "db7b0ea69298d877cdd1b97ff5b5ed33d34b38456bb49ffb9e586abd3a31bb58",
    "repeat/I106/program.bin": "6dd48201aa25587c14f1addcad6a1dd11f93ba2c0dc0afe6023344188ebf2ada",
    "repeat/I106/run/caprice.log": "a16950df11e7d8beab08994b45b3187e6d04a0da406ba65acf8314aa0ec408b8",
    "repeat/I106/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/I106/run/screen.png": "a9bf5b2f17bf42dd05583db4009b1a6782172f38e85c79e590764ea326dbcb07",
    "repeat/I126/baseline/caprice.log": "6d37ccf1306762ded419812d14145e024755f5d113638babaf29140c08f12b5c",
    "repeat/I126/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I126/capture.json": "12ba9c6634087d2697580d13eb958f48222c3a0272696f38c70198aa42a70a03",
    "repeat/I126/list/caprice.log": "13b26ec8a57095e16507dfd28cc5a091db3bb9d186b89ecc351505be81213798",
    "repeat/I126/list/screen.png": "ed4eef94aafda6abe1623a79cadfe97c9d3b3dbbdd601e3a152f9370fb388d7e",
    "repeat/I126/program.bin": "ee4a9d3a0abb0f8d9710fb44ab47a3dc2c1f45fef4eeb34e96e0afd4661285de",
    "repeat/I126/run/caprice.log": "d4dafb7b147381f87d405fc6072431fd34c2c116d6876e6c77460ed22f9a81a0",
    "repeat/I126/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/I126/run/screen.png": "58c2b5e2d12c138f7b4fa939841afa2dfdcd780a9df56fd8ec6a7c852a83a5f6",
    "repeat/I1266/baseline/caprice.log": "cc9742b362f4075d5fcb4d0af316b1c97366a53952b48651d1dbcc67b326b347",
    "repeat/I1266/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I1266/capture.json": "dc57af73cff7508b409a9830aaa446848fef2e69211b9e379e56fefbdd1eeaa2",
    "repeat/I1266/list/caprice.log": "8cb7cb4dfd8d4de1c75a6e905e0ea12515046faa72df55a5263d3806a87fa529",
    "repeat/I1266/list/screen.png": "01bdd48a7621c11b25bd552f2442c8f82de843fe813be5b89f803918abfca0b2",
    "repeat/I1266/program.bin": "627786c3816da29da184b7fa417b11c4608bf436a3909476ad3929f4df2c9c19",
    "repeat/I1266/run/caprice.log": "e63451376df74030b3d6fcfd910cf5157cbffb4dcd76577ddee90d712c481d5f",
    "repeat/I1266/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/I1266/run/screen.png": "130869840981ed84b76b7187b5972c805a7e630b029ed029f5e40d50c781d236",
    "repeat/I127/baseline/caprice.log": "6ebabb74b5e816e36ea22c6ee173be3d9e15df6fbee5891ac0ac72313ae92772",
    "repeat/I127/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I127/capture.json": "bd20ae0acdae19ec95853278ea715f0559ab8428422a8a60467baad7c7555541",
    "repeat/I127/list/caprice.log": "5a7bd5366a62313ad4625c2327c222f4aa38f6e23c6c8329237942724fa98104",
    "repeat/I127/list/screen.png": "7efe9fae7e3ab9a80a0fe3ac77ef6de5e50dafa5c866c974ec413631572213c1",
    "repeat/I127/program.bin": "51bd26d73201fb3db2cb374c7ee0b7bed0b6fe7febb99cddcce13de5f3b22663",
    "repeat/I127/run/caprice.log": "3e86ae123fd72f098aa61f7d1fd5f7491d7d41d0a7cb28abfcd05fefc42044c1",
    "repeat/I127/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/I127/run/screen.png": "3e90ff07bfb95da6c49ff40c4b4f95caf3beb3989eb013151fa5894769c35da9",
    "repeat/I131/baseline/caprice.log": "4b8a74db6abf7450582261e58a16a9cf6a58dcec77313a942eb5fd67598c4dee",
    "repeat/I131/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I131/capture.json": "d231c02e734e3265593f938f5d59839842d51a97f4076b2c0352f807183315ba",
    "repeat/I131/list/caprice.log": "d4706fe3052e3ca6f20afa6b9d388faadc5187035c668137390e2169fc9e1369",
    "repeat/I131/list/screen.png": "7d0bd60d204f0bc4bcc58ad8d05ab3567513773405f55b33085713eaaf0d32cf",
    "repeat/I131/program.bin": "95178820a8495d227b9ceec800d79ed1653a1b65a85459f3ec62759220a8d280",
    "repeat/I131/run/caprice.log": "bff97ca3e89cd354818bc3829559908610080d83feac2ef3ccf221028b7ee3ec",
    "repeat/I131/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/I131/run/screen.png": "3d861d78186a0e38232219df8e6320bddee0d38be78d8c1770df6ade7ca52a79",
    "repeat/I132/baseline/caprice.log": "c8f2f24d35ae6d7888e0bea23adde77f7ff019ddb6730c3c2ef4afa9dafa3e9b",
    "repeat/I132/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I132/capture.json": "8d1623596b5bf60b431e16eb43719ec52df9991debcb3f24cfc9b63ece5f13cf",
    "repeat/I132/list/caprice.log": "6d2d99e4ce1cb7763f818472921206e180411b0bb777fc1990e21fce8443e17d",
    "repeat/I132/list/screen.png": "30c7d76c850a670eb39a8bb4183cfc2a2d83fe636964c5c2973f66b475d0490f",
    "repeat/I132/program.bin": "0473ba5c77155018186282b14cf6688c47aae05f639fb8cb44f72c1dd6213895",
    "repeat/I132/run/caprice.log": "78a844c1b0c607cd0faf4ace3a45bb507cfbc0fd7b4f549e54e65afb6ca52038",
    "repeat/I132/run/printer.dat": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
    "repeat/I132/run/screen.png": "b74c05e40b7ba367317531a7a18fbfbe2df8edd7d9958809886456d4f61ded5a",
    "repeat/I1526/baseline/caprice.log": "8d6368f0e9ec9dd368af4982ea776a8975ca1cff5a6d3ebb163d190b3a3a0c9d",
    "repeat/I1526/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I1526/capture.json": "d9b1f38784657b0e92c75871a7ab284784addd7bfe795f125aac8326a91e4ecc",
    "repeat/I1526/list/caprice.log": "97b4ce85845669994274f1c4a598fbbc80dccc856dec94c965aa3dbece291053",
    "repeat/I1526/list/screen.png": "c9da9d372e2a32a368e27373269bec9fbabf95999b81645630ea555f54230caf",
    "repeat/I1526/program.bin": "8ff894ca9285ba1099edc38251050f7e743f82cab90c955af460134c0c43054b",
    "repeat/I1526/run/caprice.log": "659fbe3b31febe13c237ebc2a725b2a727081ce5d184593501fb27f55e9266e0",
    "repeat/I1526/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/I1526/run/screen.png": "15cd1af91a1d939ca91d9cdb3f4871866058d944c04dcad41331022d05ef4c73",
    "repeat/I1626/baseline/caprice.log": "eccfda5afcfbc2fba03ba026d85ff85dee34f2daef206c632902cd3e49fd1301",
    "repeat/I1626/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I1626/capture.json": "52f82c7a498295fbd0693ce082fd3185fe0d93f91be3ccaa027e306e1e90e756",
    "repeat/I1626/list/caprice.log": "4c688100d4024351cb9b3930d88961f86a041e7b38d9ed576795a4e4e759fe65",
    "repeat/I1626/list/screen.png": "0467757653d49b84044fa7cf07a0fe68529eeb9480770c2b23fc1b0936b07a72",
    "repeat/I1626/program.bin": "d62a66f084b65cf5f2a21330d23939f845776f2302a822a0da95a1fd9fffed24",
    "repeat/I1626/run/caprice.log": "82b9fe44ab8763e718265cec15b6e7640abe7989bae356a2093e9d6c4e3a1c36",
    "repeat/I1626/run/printer.dat": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
    "repeat/I1626/run/screen.png": "2d7f7472cdafc258fe00a09a12edb3d85223435b5e2d72c1d24199206f01ea71",
    "repeat/I1N1/baseline/caprice.log": "37c60c1b9610540d0c8728f1e6cb01810651cafd62af1107e8ebf1fcd495c625",
    "repeat/I1N1/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I1N1/capture.json": "60c7d3f4747024c744ac342e100e5b2fc22e23d880922ad8386ca769f58d77a1",
    "repeat/I1N1/list/caprice.log": "8eb88a1d6a6ae2d1aaad7869cfa8495403b084859504c6229233ce2089ed39ed",
    "repeat/I1N1/list/screen.png": "62ed15005160e8298ec97608dde7af620cedaa4c9466c0a37752525d55c78d1e",
    "repeat/I1N1/program.bin": "039c57c82cd44d22367dfed410ee6d4c0da30e81cf378e35f14fa0c1f3fd3bfa",
    "repeat/I1N1/run/caprice.log": "03cb2f61aaa0ed69f31dae81f8f5be1f2e02b6474c7bd5ddc879c7afa93466a2",
    "repeat/I1N1/run/printer.dat": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
    "repeat/I1N1/run/screen.png": "bd13b56cf00e0f0018167214b619eca8579d08c300cbddb779adb57697e11219",
    "repeat/I206/baseline/caprice.log": "f8d6d79dc1f6eca9db592c296a9b006277ae3a865f08784995c111cd99dc48a4",
    "repeat/I206/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I206/capture.json": "70cf7ef0e9fba5709bc36d606351e4b17cfd5a712213c6417fd97d1e2c8708bf",
    "repeat/I206/list/caprice.log": "ece9a0ea8cdf0ce08435b3ff7579690cffea5d90b8d4cb43d72bd6519d2b6375",
    "repeat/I206/list/screen.png": "2e96b7a47a56681dd1460a4ab6e669fb1e1acad56d3e5ac3f255bd177c9e99b5",
    "repeat/I206/program.bin": "ef310cd0f3523059ccef31114b1e54a9dee1cc3c4a6d23ca058ff22e20043ba3",
    "repeat/I206/run/caprice.log": "9e13aace1dc6245b311fe910226695cd460fedf011e3283466f1fe90694d4c54",
    "repeat/I206/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/I206/run/screen.png": "b69a6d45565bed901cdfbb6f53f859da6a4c853cd326c743858db00899ce532e",
    "repeat/I318/baseline/caprice.log": "74c6c84ff5dc1c7809d54a576d6a8d32237f16b7fe940d6569aa988a99329995",
    "repeat/I318/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/I318/capture.json": "49019081c65539c5e01614a3e52bd0a704be69cf692cb2f5d70cb5863c999c4c",
    "repeat/I318/list/caprice.log": "ac56d3ebb230d14ae24b1e5754ac07f3462137149cb780df4f080d39cefe0293",
    "repeat/I318/list/screen.png": "87de8a7f3baa991cf79730a4641d445af68f13e59b82e65c955ca8a92c45eef4",
    "repeat/I318/program.bin": "610fff221ad4726b45d6ed1a244da209954f1fdbb6910173afa5e43ecc994c6d",
    "repeat/I318/run/caprice.log": "0fb4dfa87ebbbebe9677387982bc164416e815a0812339e8b47eca411ab9a82e",
    "repeat/I318/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/I318/run/screen.png": "2a06b2a5640a146f233d4d08712f3aedb8107b725c4d0786f8f608397f04f6f2",
    "repeat/IN126/baseline/caprice.log": "4cc8ae2e483db8de2c4880c20d0c921bf2f11cc875f5736e526d2120bbcbdeb2",
    "repeat/IN126/baseline/screen.png": "19cb811c63d97aa5e8f74864418e6d38eb4a907867b5bd83e2a563634c0c513d",
    "repeat/IN126/capture.json": "5aa01c5e1784e3c599bc9dfe271e1e8ce23cb2aeed77dfd066c634a7c868ab87",
    "repeat/IN126/list/caprice.log": "b6a34c65f286867a3702e8a2fc2afa7dfccf41599f54e2b2849079ea0b009e56",
    "repeat/IN126/list/screen.png": "246eed7740f6c8c0906bdd4a409599936e8723e2e273be677307e5ac2981a057",
    "repeat/IN126/program.bin": "234fe829bd9c1774d88a4505050368fbcdff629b0b8eae483d18128c921f51e7",
    "repeat/IN126/run/caprice.log": "aa2f3502c4a9df9bdccd504d68aa664b23779015cd58d548cd9fd38fe92f96cc",
    "repeat/IN126/run/printer.dat": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
    "repeat/IN126/run/screen.png": "c0f800b0f78866ec6e71dee961475838b9ec982d7469ded72c6ce26adfcb05c5",
}
SEALED_MANIFEST = "58e8de0bf839d21699ff220aa6d2b0ca325dc6c7586c595b9baf6acb8d373aed"
ACQUISITION_HEAD = '6e9b17b8d545a57ef3942f217c9b4d3daeae8c38'
# Entire first CPC line, including its byte length and 00 terminator, taken
# from the real 26-session Caprice32 Actions logs; never inferred from ROM.
CASE_RECORDS = {
    'I00':   '0A 00 0A 00 A2 20 0E 2C 0E 00',
    'I126':  '0B 00 0A 00 A2 20 0F 2C 19 1A 00',
    'I106':  '0A 00 0A 00 A2 20 0F 2C 14 00',
    'I206':  '0A 00 0A 00 A2 20 10 2C 14 00',
    'I318':  '0B 00 0A 00 A2 20 11 2C 19 12 00',
    'I1526': '0C 00 0A 00 A2 20 19 0F 2C 19 1A 00',
    'I127':  '0B 00 0A 00 A2 20 0F 2C 19 1B 00',
    'I131':  '0B 00 0A 00 A2 20 0F 2C 19 1F 00',
    'I1266': '0D 00 0A 00 A2 20 0F 2C 19 1A 2C 14 00',
    'I1626': '0C 00 0A 00 A2 20 19 10 2C 19 1A 00',
    'IN126': '0C 00 0A 00 A2 20 F5 0F 2C 19 1A 00',
    'I132':  '0B 00 0A 00 A2 20 0F 2C 19 20 00',
    'I1N1':  '0B 00 0A 00 A2 20 0F 2C F5 0F 00',
}




class Invalid(ValueError):
    pass


def require(test, code):
    if not test:
        raise Invalid(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink(), 'MISSING_OR_SYMLINK_' + str(path))
    return path.read_bytes()


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, indent=2) + '\n').encode('ascii')


def source(case):
    require(case in CASES, 'UNKNOWN_CASE')
    expected = (f'10 INK {CASES[case]}\n20 LOCATE 1,15\n'
                '30 PRINT "J118INK"\n40 END\n').encode('ascii')
    require(read(SOURCES / (case.lower() + '.bas')) == expected,
            'SOURCE_DRIFT_' + case)
    return expected


def check_head(expected):
    require(bool(re.fullmatch(r'[0-9a-f]{40}', expected)), 'INVALID_EXPECTED_HEAD')
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                   text=True).strip()
    require(head == expected, 'EXPECTED_HEAD_MISMATCH expected=' + expected + ' actual=' + head)
    return head


def check_caprice(cap):
    require(subprocess.check_output(['git', '-C', str(cap), 'rev-parse', 'HEAD'],
                                    text=True).strip() == cpc.PIN, 'CAPRICE_PIN_MISMATCH')
    require(sha(read(cap / 'rom/cpc6128.rom')) == cpc.ROM_SHA, 'ROM_SHA_MISMATCH')
    require((cap / 'cap32').is_file(), 'CAPRICE_EXECUTABLE_MISSING')
    return subprocess.check_output([str(cap / 'cap32'), '--version'],
                                   cwd=cap, text=True).strip()


def launch(cap, dest, snadir, commands, printer, shots=1):
    dest.mkdir(parents=True, exist_ok=False)
    cfg = configparser.ConfigParser(interpolation=None)
    require(bool(cfg.read(cap / 'cap32.cfg')), 'CAPRICE_CONFIG_MISSING')
    cfg['system'].update(model='2', ram_size='128', speed='4', auto_pause='0',
                         printer='1' if printer else '0', mf2='0', keyboard='0',
                         boot_time='42', limit_speed='0', resources_path=str(cap / 'resources'))
    cfg['control']['kbd_layout'] = '0'
    cfg['sound']['enabled'] = '0'
    cfg['video'].update(scr_style='1', scr_window='1')
    cfg['file']['printer_file'] = str(dest / 'printer.dat')
    cfg['file']['snap_path'] = str(snadir)
    cfg['file']['sdump_dir'] = str(dest)
    cfg['rom']['rom_path'] = str(cap / 'rom')
    cfg['rom']['slot07'] = 'amsdos.rom'
    cfg['rom']['rom_mf2'] = ''
    config = dest / 'cap32.cfg'
    with config.open('w', encoding='utf-8') as f:
        cfg.write(f, space_around_delimiters=False)
    argv = ['xvfb-run', '-a', str(cap / 'cap32'), '-c', str(config)]
    for command in commands:
        argv.extend(['-a', command.replace('CAP32_SNAPSHOT', '\x0c\x0d')])
    start = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(argv, cwd=cap,
                            env=dict(os.environ, SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='x11'),
                            capture_output=True, timeout=90, check=False)
    stop = datetime.now(timezone.utc).isoformat()
    (dest / 'caprice.log').write_bytes(b'exit code: ' + str(result.returncode).encode()
                                      + b'\n' + result.stdout + b'\n[stderr]\n' + result.stderr)
    config.unlink()
    require(result.returncode == 0, 'CAPRICE_EXECUTION_ERROR_' + repr(result.stderr[-400:]))
    pics = list(dest.glob('screenshot_*.png'))
    require(len(pics) == shots and all(read(p).startswith(b'\x89PNG\r\n\x1a\n')
                                       for p in pics), 'PNG_COUNT_OR_SIGNATURE_INVALID')
    pics = sorted(pics)
    for i, src in enumerate(pics):
        src.rename(dest / ('screen.png' if shots == 1 else f'screen_{i}.png'))
    data = read(dest / ('screen.png' if shots == 1 else 'screen_0.png'))
    require(len(data) >= 80 and data[12:16] == b'IHDR', 'PNG_MISSING_IHDR')
    w = int.from_bytes(data[16:20], 'big')
    h = int.from_bytes(data[20:24], 'big')
    require(300 <= w <= 2000 and 200 <= h <= 1500, 'PNG_UNEXPECTED_DIMENSIONS')
    return {'started_utc': start, 'finished_utc': stop,
            'commands': commands, 'screenshot_width': w, 'screenshot_height': h}


def capture_one(cap, out, case, session, tmp):
    src = source(case)
    work = out / session / case
    ldir, rdir, bdir = work / 'list', work / 'run', work / 'baseline'
    lsnap = tmp / (case + '_' + session)
    lsnap.mkdir()
    raw_lines = src.decode('ascii').splitlines()
    cmd_list = setup(case) + raw_lines + [
        'LIST', 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT']
    lt = launch(cap, ldir, lsnap, cmd_list, False)
    snapshots = list(lsnap.glob('*.sna'))
    require(len(snapshots) == 1, 'LIST_SNAPSHOT_MISSING')
    program, region = cpc.extract_snapshot(read(snapshots[0]), LINES)
    nums, rows = cpc.records(program)
    first = program[rows[0]['offset']:rows[0]['offset'] + rows[0]['length']]
    require(first[4] == 0xa2, 'CPC_INK_OPCODE_NOT_A2')
    (work / 'program.bin').write_bytes(program)

    # A genuine baseline glyph before INK; does not infer any RGB from #8.
    cmd_baseline = setup(case) + ['LOCATE 1,15', 'PRINT "J118INK"',
                                 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT']
    bt = launch(cap, bdir, tmp, cmd_baseline, False)
    cmd_run = setup(case) + raw_lines + ['RUN',
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
        'PRINT #8,ERR', 'PRINT #8,ERL', 'CAP32_DELAY CAP32_EXIT']
    rt = launch(cap, rdir, tmp, cmd_run, True)
    raw = read(rdir / 'printer.dat')
    require(0 < len(raw) <= 256, 'ERR_ERL_PRINTER_MISSING')
    parsed = [parse_integer(row) for row in raw.splitlines(keepends=True)]
    require(len(parsed) == 2 and all(p is not None for p in parsed),
            'ERR_ERL_NOT_TWO_NUMBERS')
    err, erl = (p['numeric_value'] for p in parsed)
    rec = {
        'case':case, 'session':session, 'source_sha256':sha(src),
        'program_sha256':sha(program), 'program_hex':program.hex(' ').upper(),
        'ink_record_hex':first.hex(' ').upper(), 'ink_opcode_observed':first[4],
        'region':region, 'line_numbers':nums, 'setup_mode':1,
        'setup_commands':setup(case), 'paper':0, 'pen':1,
        'print_location': {'column':1,'row':15,'text':'J118INK'},
        'list':lt, 'baseline':bt, 'run':rt, 'err':err,'erl':erl,
        'run_kind':'ERROR' if err else 'NO_ERROR',
        'printer_sha256':sha(raw),
        'list_png_sha256':sha(read(ldir/'screen.png')),
        'baseline_png_sha256':sha(read(bdir/'screen.png')),
        'run_png_sha256':sha(read(rdir/'screen.png')),
        'list_log_sha256':sha(read(ldir/'caprice.log')),
        'baseline_log_sha256':sha(read(bdir/'caprice.log')),
        'run_log_sha256':sha(read(rdir/'caprice.log')),
        'visual_classification':'VISUAL_UNVERIFIED',
        'temporal_classification':('TEMPORAL_UNVERIFIED' if case == 'I1266' else 'NOT_APPLICABLE'),
        'screen_is_not_token_evidence':True,'printer_is_not_color_evidence':True,
    }
    (work/'capture.json').write_bytes(encoded(rec))
    return rec


def capture_chronology(cap, out, session, tmp):
    # Same physical Caprice32 process: initial red text, then INK 1,26.
    # No PRINT between two screenshots. Two separate processes for original/repeat.
    dest = out/session/'chronology'
    cmds = CHRONO + ['INK 1,6', 'LOCATE 1,15', 'PRINT "J118INK"',
                    'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                    'INK 1,26',
                    CHRONO_DELAY + ' CAP32_SCRNSHOT CAP32_EXIT']
    chron = launch(cap,dest,tmp,cmds,False,shots=2)
    r = {'session':session,'commands':cmds,'caprice':chron,
         'before_sha256':sha(read(dest/'screen_0.png')),
         'after_sha256':sha(read(dest/'screen_1.png')),
         'no_intervening_print':True,'visual_classification':'VISUAL_UNVERIFIED'}
    (dest/'capture.json').write_bytes(encoded(r))
    return r


def acquire(cap, out, head):
    require(not out.exists(), 'EVIDENCE_OUTPUT_EXISTS')
    version = check_caprice(cap)
    out.mkdir(parents=True)
    manifest = {'schema_version':1,'phase':PHASE,'acquisition_head':head,
                'run_id':os.environ.get('GITHUB_RUN_ID','LOCAL'),
                'oracle':{'caprice':cpc.PIN,'rom':cpc.ROM_SHA,'ghcr':GHCR,
                          'version':version,'model':'CPC6128','basic':'1.1'},
                'full_snapshots_archived':False,'native_changes':False,
                'cases':{}, 'chronology':{},
                'visual_classification':'VISUAL_UNVERIFIED',
                'temporal_classification':'TEMPORAL_UNVERIFIED'}
    with tempfile.TemporaryDirectory(prefix='j118-ink-sna-') as tmp:
        t=Path(tmp)
        for case in CASES:
            seen={}
            for session in SESSIONS:
                seen[session]=capture_one(cap,out,case,session,t)
                print(PHASE,case,session,'RECORD',seen[session]['ink_record_hex'],
                      'ERR',seen[session]['err'],'ERL',seen[session]['erl'],flush=True)
            require(seen['original']['program_hex']==seen['repeat']['program_hex'],
                    'INDEINKDENT_RAM_MISMATCH_'+case)
            require((seen['original']['err'],seen['original']['erl'])==
                    (seen['repeat']['err'],seen['repeat']['erl']),
                    'INDEINKDENT_ERR_ERL_MISMATCH_'+case)
            manifest['cases'][case]={x:sha(read(out/x/case/'capture.json'))
                                      for x in SESSIONS}
        for session in SESSIONS:
            chron=capture_chronology(cap,out,session,t)
            manifest['chronology'][session]=sha(read(out/session/'chronology/capture.json'))
            print(PHASE,'CHRONOLOGY',session,chron['before_sha256'],
                  chron['after_sha256'],flush=True)
    (out/'manifest.json').write_bytes(encoded(manifest))
    verify(out)
    print(PHASE,'CPC_ACQUIRED',len(CASES)*2,
          'CASE_SESSIONS_PLUS_2_CHRONOLOGY HEAD',head,flush=True)


def verify(out, permanent=False):
    m=json.loads(read(out/'manifest.json'))
    require(m['phase']==PHASE and m['schema_version']==1 and
            bool(re.fullmatch(r'[0-9a-f]{40}',m['acquisition_head'])) and
            (not permanent or m['acquisition_head']==ACQUISITION_HEAD) and
            m['oracle']['caprice']==cpc.PIN and m['oracle']['rom']==cpc.ROM_SHA and
            m['oracle']['ghcr']==GHCR and m['oracle']['model']=='CPC6128' and
            m['native_changes'] is False and m['full_snapshots_archived'] is False and
            m['visual_classification']=='VISUAL_UNVERIFIED' and
            m['temporal_classification']=='TEMPORAL_UNVERIFIED' and
            set(m['cases'])==set(CASES) and set(m['chronology'])==set(SESSIONS),
            'MANIFEST_PROVENANCE')
    anc=subprocess.run(['git','-C',str(ROOT),'merge-base','--is-ancestor',
                        m['acquisition_head'],'HEAD'],stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
    require(anc.returncode==0,'FALSE_OR_UNREACHABLE_ACQUISITION_HEAD')
    if permanent:
        require(bool(re.fullmatch(r'[a-f0-9]{64}',SEALED_MANIFEST)) and
                sha(read(out/'manifest.json'))==SEALED_MANIFEST,
                'EXTERNAL_MANIFEST_SEAL')
        require(bool(SEALED) and set(SEALED)=={str(p.relative_to(out))
            for p in out.rglob('*') if p.is_file() and p.name != 'manifest.json'},
            'EXTERNAL_ARCHIVE_FILE_INVENTORY')
        for name,expected in SEALED.items():
            require(sha(read(out/name))==expected,'EXTERNAL_SHA_'+name)
    records={}
    for case in CASES:
        seen=[]
        for session in SESSIONS:
            work=out/session/case
            files={
                'program':read(work/'program.bin'),
                'capture':read(work/'capture.json'),
                'printer':read(work/'run/printer.dat'),
                'list_png':read(work/'list/screen.png'),
                'run_png':read(work/'run/screen.png'),
                'baseline_png':read(work/'baseline/screen.png'),
                'list_log':read(work/'list/caprice.log'),
                'run_log':read(work/'run/caprice.log'),
                'baseline_log':read(work/'baseline/caprice.log')}
            d=json.loads(files['capture'])
            require(sha(files['capture'])==m['cases'][case][session] and
                    d['source_sha256']==sha(source(case)) and
                    d['program_sha256']==sha(files['program']) and
                    d['program_hex']==files['program'].hex(' ').upper() and
                    d['case']==case and d['session']==session and
                    d['line_numbers']==LINES and d['setup_commands']==setup(case) and
                    d['paper']==0 and d['pen']==1 and d['setup_mode']==1 and
                    d['print_location']=={'column':1,'row':15,'text':'J118INK'} and
                    d['screen_is_not_token_evidence'] and
                    d['printer_is_not_color_evidence'] and
                    d['visual_classification']=='VISUAL_UNVERIFIED',
                    'CAPTURE_PROVENANCE_'+case+session)
            numbers,rows=cpc.records(files['program'])
            first=files['program'][:rows[0]['length']]
            require(numbers==LINES and first[4]==0xa2 and
                    d['ink_opcode_observed']==0xa2 and
                    d['ink_record_hex']==first.hex(' ').upper() and
                    (not permanent or d['ink_record_hex']==CASE_RECORDS[case]) and
                    d['region']['length']==len(files['program']) and
                    d['region']['line_numbers']==LINES,
                    'RAM_TOKEN_OR_VALUE_'+case+session)
            for label in ('list','baseline','run'):
                png=files[label+'_png']
                require(png.startswith(b'\x89PNG\r\n\x1a\n') and
                        png[12:16]==b'IHDR' and sha(png)==d[label+'_png_sha256'] and
                        d[label]['screenshot_width']==int.from_bytes(png[16:20],'big') and
                        d[label]['screenshot_height']==int.from_bytes(png[20:24],'big'),
                        'PNG_HASH_AND_FORMAT_'+case+session+label)
                require(sha(files[label+'_log'])==d[label+'_log_sha256'] and
                        files[label+'_log'].startswith(b'exit code: 0\n'),
                        'CAPRICE_LOG_'+case+session+label)
            lines=[parse_integer(z) for z in files['printer'].splitlines(keepends=True)]
            require(len(lines)==2 and all(z is not None for z in lines) and
                    [z['numeric_value'] for z in lines]==[d['err'],d['erl']] and
                    d['run_kind']==('ERROR' if d['err'] else 'NO_ERROR') and
                    sha(files['printer'])==d['printer_sha256'],
                    'ERR_ERL_'+case+session)
            require(d['list']['commands']==setup(case)+source(case).decode('ascii').splitlines()+
                    ['LIST','CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT'] and
                    d['baseline']['commands']==setup(case)+['LOCATE 1,15','PRINT "J118INK"',
                    'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT'] and
                    d['run']['commands']==setup(case)+source(case).decode('ascii').splitlines()+
                    ['RUN','CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                     'PRINT #8,ERR','PRINT #8,ERL','CAP32_DELAY CAP32_EXIT'],
                    'COMMAND_CHRONOLOGY_'+case+session)
            seen.append(d)
        require(seen[0]['program_hex']==seen[1]['program_hex'] and
                (seen[0]['err'],seen[0]['erl'])==(seen[1]['err'],seen[1]['erl']),
                'PAIR_RAM_ERR_ERL_'+case)
        records[case]=seen[0]['ink_record_hex']
    require(len(set(records.values()))==len(CASES),
            'SOURCE_TOKEN_RECORD_REUSED')
    chrono_cmds=CHRONO+['INK 1,6','LOCATE 1,15','PRINT "J118INK"',
                        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT','INK 1,26',
                        CHRONO_DELAY + ' CAP32_SCRNSHOT CAP32_EXIT']
    for session in SESSIONS:
        dest=out/session/'chronology'
        rec=json.loads(read(dest/'capture.json'))
        require(m['chronology'][session]==sha(read(dest/'capture.json')) and
                rec['session']==session and rec['commands']==chrono_cmds and
                rec['no_intervening_print'] is True and
                rec['visual_classification']=='VISUAL_UNVERIFIED' and
                rec['before_sha256']==sha(read(dest/'screen_0.png')) and
                rec['after_sha256']==sha(read(dest/'screen_1.png')) and
                read(dest/'caprice.log').startswith(b'exit code: 0\n'),
                'CHRONOLOGY_SOURCE_AND_SHA_'+session)
    print(PHASE,'VERIFIED',len(CASES)*2,'sessions',
          'EXTERNAL' if permanent else 'UNSEALED',flush=True)


def negatives(out, permanent=False):
    variants=['token','value','capture','internal_sha','pair','head','missing','png_roi','manifest_sha']
    if permanent:variants.append('coordinated')
    untouched={str(p.relative_to(out)):sha(read(p)) for p in out.rglob('*') if p.is_file()}
    for variant in variants:
        with tempfile.TemporaryDirectory(prefix='j118-ink-fraud-') as tmp:
            clone=Path(tmp)/'clone'
            shutil.copytree(out,clone)
            item=clone/'original/I126'
            rec_path=item/'capture.json'
            rec=json.loads(read(rec_path))
            if variant in ('token','value','coordinated'):
                b=bytearray(read(item/'program.bin'))
                b[4 if variant=='token' else 8]^=1
                (item/'program.bin').write_bytes(b)
                if variant=='coordinated':
                    rec['program_sha256']=sha(b)
                    rec['program_hex']=b.hex(' ').upper()
                    rec['ink_record_hex']=b[:int.from_bytes(b[:2],'little')].hex(' ').upper()
                    rec_path.write_bytes(encoded(rec))
                    man=json.loads(read(clone/'manifest.json'))
                    man['cases']['I126']['original']=sha(read(rec_path))
                    (clone/'manifest.json').write_bytes(encoded(man))
            elif variant=='capture':
                b=bytearray(read(item/'run/screen.png'));b[-1]^=1
                (item/'run/screen.png').write_bytes(b)
            elif variant=='internal_sha':
                rec['run_png_sha256']='0'*64;rec_path.write_bytes(encoded(rec))
            elif variant=='pair':
                other=clone/'repeat/I126/capture.json'
                other.write_bytes(read(rec_path))
                man=json.loads(read(clone/'manifest.json'))
                man['cases']['I126']['repeat']=sha(read(other))
                (clone/'manifest.json').write_bytes(encoded(man))
            elif variant=='manifest_sha':
                man=json.loads(read(clone/'manifest.json'))
                man['temporal_classification']='FORGED_CPC_TEMPORAL'
                (clone/'manifest.json').write_bytes(encoded(man))
            elif variant=='head':
                man=json.loads(read(clone/'manifest.json'))
                man['acquisition_head']='0'*40
                (clone/'manifest.json').write_bytes(encoded(man))
            elif variant=='missing':
                (item/'run/printer.dat').unlink()
            elif variant=='png_roi':
                b=bytearray(read(item/'baseline/screen.png'));b[-20]^=1
                (item/'baseline/screen.png').write_bytes(b)
            try: verify(clone,permanent)
            except (Invalid,ValueError,KeyError,IndexError,OSError) as ex:
                print(PHASE,'FALSIFICATION_REJECTED',variant,str(ex)[:100],flush=True)
            else:raise Invalid('FALSIFICATION_ACCEPTED_'+variant)
    for rel,digest in untouched.items():
        require(sha(read(out/rel))==digest,'ARCHIVE_MUTATED_'+rel)
    print(PHASE,'ARCHIVE_INTACT',len(untouched),flush=True)


def unit():
    for case in CASES:source(case)
    cpc.self_test()
    require(len(CASES)==13 and len(SESSIONS)==2,'MATRIX_DRIFT')
    try:check_head('0'*40)
    except Invalid as ex:
        require('EXPECTED_HEAD_MISMATCH' in str(ex),'FALSE_HEAD_NOT_REJECTED')
    else:raise Invalid('FALSE_HEAD_ACCEPTED')
    print(PHASE,'SOURCE_MATRIX_FALSE_HEAD_PASS')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check-sources', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--permanent', action='store_true')
    p.add_argument('--expect-head')
    p.add_argument('--caprice', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--evidence', type=Path)
    a = p.parse_args()
    if a.expect_head:
        check_head(a.expect_head)
    if a.check_sources or a.self_test:
        unit()
    if a.caprice:
        require(a.output is not None and a.evidence is None, 'ACQUIRE_ARGUMENTS')
        head = check_head(a.expect_head or subprocess.check_output(
            ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip())
        acquire(a.caprice.resolve(), a.output.resolve(), head)
    if a.evidence:
        verify(a.evidence.resolve(), a.permanent)
        if a.self_test:
            negatives(a.evidence.resolve(), a.permanent)
    else:
        require(not a.permanent, 'PERMANENT_REQUIRES_EVIDENCE')
    require(a.check_sources or a.self_test or a.caprice or a.evidence,
            'NO_OPERATION_SELECTED')


if __name__ == '__main__':
    try:
        main()
    except (Invalid, OSError, subprocess.SubprocessError, UnicodeError,
            KeyError, IndexError, json.JSONDecodeError) as err:
        print('J1.18-A FAIL', err, file=sys.stderr)
        sys.exit(1)
