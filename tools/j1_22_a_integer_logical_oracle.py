#!/usr/bin/env python3
"""J1.22-A: CPC6128 INTEGER logical-expression acquisition and sealed verifier.

A source program or a host calculation is NEVER an oracle measurement. An
independent original Actions artifact must supply immutable external seals
before --verify is allowed to succeed. --acquire only runs pinned CPC ROM.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'tests/fixtures/cpc6128/j1_22_a_integer_logical'
BASE = '1d5edc630390bfb109d6596693ec63c8d8588a28'
PHASE = 'J1.22-A'
ROM = '31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562'
CAPRICE = '8c778bf072a06fb7c23b9cccd179041db7f79a52'
GHCR = ('ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:'
        '7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c')
CORPUS_SHA256 = 'b6be133ea38a6be5a1cb87fea4d77352fa1ac7a814eed1c115feaf8bb30b7d4e'
SESSIONS = ('original', 'repeat')
FILESET = ('program.bin', 'capture.json', 'list/caprice.log',
           'list/screen.png', 'list/printer.dat', 'run/caprice.log',
           'run/screen.png', 'run/printer.dat')
ERR_TAG = b'@@J122ERR@@'
# IMPORTANT: Never fill these using the candidate archive or a host prediction.
# Copy and audit independently from the ORIGINAL GH Actions artifact.
EXTERNAL_MANIFEST_SHA256 = 'f77f770972ddf8f3710b43a36e43fd554a11edd9c98b099ac26497a514f49b92'
EXTERNAL_ACQUISITION_HEAD = '787af8a9159d573c3f6444248666001e3b159ce8'
EXTERNAL_FILE_SHA256 = {
    'original/A00_ZERO/capture.json': '88f2dd5ca5ead270592d21c4d4c9c147523699d740070384fd46ce371e26a803',
    'original/A00_ZERO/list/caprice.log': 'a20380be95ac809675798309973de85de09615710fdf8acc6ad0f9e90e28e42b',
    'original/A00_ZERO/list/printer.dat': '97b14bb79fba58a325e821f77ac07de7c3be60c53f2f0edd7f8d10eb00a26098',
    'original/A00_ZERO/list/screen.png': '2c9de5255930c80898a9158f21610d2198c8f5681c860e459e3bcb057232e0d8',
    'original/A00_ZERO/program.bin': '76735dab385e1bd27e6112d1e38944c688a652e8901c5172146079462ee185fc',
    'original/A00_ZERO/run/caprice.log': '680dd94fe4c2beed5fd23b98b97c8a92fb1a15c0cbae7ea1121a23ad1fe09ada',
    'original/A00_ZERO/run/printer.dat': 'dd92699746263fd7c9cf2b5c6d020c7db3917497b084609039d05437439f23ff',
    'original/A00_ZERO/run/screen.png': '8e68092a0f1aad48046c438c0e4066f7c4cdea064d0ee069a2eb26950a4b47c1',
    'original/A01_POS/capture.json': '465d5e48b353ab60939d24839b24babc86909d424c39751e4d079cdbd2e0cf64',
    'original/A01_POS/list/caprice.log': 'd25d6941a019c071b85e0655183b724c264f3c19b89f15037e9be8e2a097d9d3',
    'original/A01_POS/list/printer.dat': '5dc9cb6cfef95cab817a4a23f7feafd7a6150373ad462123b6f4bf1dba84c3c2',
    'original/A01_POS/list/screen.png': 'd255758f703e3c417b51347106d65d1f4541042cd49b9355ace9eae40dba9728',
    'original/A01_POS/program.bin': '73ab37e8a0575d292944eb50c9ca79ad9a1e1fb98cf0fbdf5424f299666070ea',
    'original/A01_POS/run/caprice.log': '1b5c04fb1b2376c4a0af2e51ba79d894b33e7e8c0d65f8408b7d9417201bb88d',
    'original/A01_POS/run/printer.dat': 'd0e142521557aa895fb5bf7650810513919d0e81f8b46e1757e288d0f9ce1fad',
    'original/A01_POS/run/screen.png': 'e7c59510b3029f67f6c10df6e9de45f1242eea8cafb44c0bde1dd2466688f991',
    'original/A02_NEG/capture.json': '9d1d8fecc5d88bc4905eec3a2e1c3bc6fe651c075f918d09153189ca32ae2515',
    'original/A02_NEG/list/caprice.log': '05fdda303cbb4c21fc92a639cd04b14250f9c2d24928040d79c64b57c473e6ad',
    'original/A02_NEG/list/printer.dat': '14afba5b0afacbd9be2b79c653af0d7491b6ae20daef5d20a40a100d49f787db',
    'original/A02_NEG/list/screen.png': '27e30a7ed1648720e8e574f5de9ca715b8a512325ce8912a92b12a17849a3954',
    'original/A02_NEG/program.bin': '212bfdcf7bd2b743b68bd2e648d325cf2437ea8d632422da787053aaad014af9',
    'original/A02_NEG/run/caprice.log': '2a0e1927971f6148b3fedd51b61736008d107bf0466131b4ee0874846b173b61',
    'original/A02_NEG/run/printer.dat': '22e01b30dfcc20e32a4db2de817e882354dd0743ba0ed44b0248595af4c74f0c',
    'original/A02_NEG/run/screen.png': '0f64ef25ec5e61f0644b671941621c1b1c96cd1683b354af19bb0c447ef597a1',
    'original/A03_MIN/capture.json': '95b4d9feced680ab6919a1329edf5d1174be76a101fda978976996f7e7b37980',
    'original/A03_MIN/list/caprice.log': 'cab4258e819f25095f091c10b34c3faf34f68922504e4e22bc1fbbe22e984a51',
    'original/A03_MIN/list/printer.dat': '90b967e04bd093616e04e9b81976e342d08e75804bc8cfda04d299dfd1141c6a',
    'original/A03_MIN/list/screen.png': '467684b48edccf3786088b4fd250c3209abd35e1ae5ea07132e4213601f1b5ad',
    'original/A03_MIN/program.bin': 'ce7da9cbf5fc15c79b3b86bec29a248d53c4f3e2a3c776d5c1f528c68d121b06',
    'original/A03_MIN/run/caprice.log': 'c61a085c66c7ded3d82a3ab6bf7f9e8e445dd7aec74a583631abc950b9b5b14c',
    'original/A03_MIN/run/printer.dat': '854ec3b4b75c35ae40f8cb9c21fdb12eda247c3e22e6a7a09d3eac005746b0a5',
    'original/A03_MIN/run/screen.png': 'a1562c9927104c5e7732d6a6dc62e46533d85ef29dbd937bc07fdeddccd74a86',
    'original/E01_DIV0/capture.json': '8d6d633427ee04b88b98bd3901d6e57345694a6810d72dff11dd57eb26a12225',
    'original/E01_DIV0/list/caprice.log': '751ae451be495fe2b2683d8bb6d8348d1de3a02a7352118efb4c071636c2f454',
    'original/E01_DIV0/list/printer.dat': '74b0182803a4f188f503b1eb5a0461a4a6be713306873a2eb752496d027e86ab',
    'original/E01_DIV0/list/screen.png': 'a82aeb110fed709f5285270baa94dd988db137bf970e0a6a5821a0d28075bbf8',
    'original/E01_DIV0/program.bin': 'f0b991ac09e42d286417082f27e14fb64ed16d2fa794d6a98cb98c60e68646b4',
    'original/E01_DIV0/run/caprice.log': '3f5a7d1d70d97d0a937aad3b2357b996276845a446ffc2328573aedfd6c5ad48',
    'original/E01_DIV0/run/printer.dat': 'adde6b118bc50f80858dcc271812f24829cc74edb6633fa0566b11f6e33bbcfd',
    'original/E01_DIV0/run/screen.png': '681596a95b1a7c3c88bab885dca64287ed220858a77a8dc52448a1ca3047ede0',
    'original/E02_OVERFLOW/capture.json': 'dc12ea282c87c04862319207d18818cceab160bdb1b4f35274996653f28b0f24',
    'original/E02_OVERFLOW/list/caprice.log': '58a36d8cdf031a45e50ea2b473e9a653754eda08ccd27fe6972ffa4af136f907',
    'original/E02_OVERFLOW/list/printer.dat': '1239cfb823bfb7fb72fb145e2be7270ecda4d547f2d9e8b1b510038545ea1e34',
    'original/E02_OVERFLOW/list/screen.png': '55c6b28143dd3f6cf4679a1f341f422566d5efe38e33394a9442f72613618959',
    'original/E02_OVERFLOW/program.bin': '6b6cf3a0dcd32ad76a85b131c4cc4f71c12789d532953d60a164fb944a0e6601',
    'original/E02_OVERFLOW/run/caprice.log': '4e032a8ce1a2fbb14b9962d8fe2a94afc2b4cb56bbf5c941d27ce7673d863f38',
    'original/E02_OVERFLOW/run/printer.dat': 'f682061d9f57dffd070c22a03903840f8692a4ef82770287c9c33e740522d3e4',
    'original/E02_OVERFLOW/run/screen.png': '2183b0561cfb8ec6b21e761b37ffcc22b0eff4bb2af21642c708696b413056ea',
    'original/N00_ZERO/capture.json': 'f3d5186c78536d17cef2d1500fe055c153bf6919243d43b804f93bc9bfacf0a0',
    'original/N00_ZERO/list/caprice.log': '44bd599aafb9377405f0eb894578156bdf763273f192b81ea60e70c59aeefc72',
    'original/N00_ZERO/list/printer.dat': 'dd026bb695b84f8a56c47284233c517517609e6bcaf34083c354ef64507c29b5',
    'original/N00_ZERO/list/screen.png': '0c7ac44eeff50977c47ccbf1ba0059ecec545311675432849a1c7bac2dcd72c8',
    'original/N00_ZERO/program.bin': '55c557fcadc2b76d2a758ada4679dcdc3e4ac31e70441fa9fe1f07f8fdb236a6',
    'original/N00_ZERO/run/caprice.log': '56db684d4a66aca445fed62472a2c4bbbf6f7e6f8f356ec4e1a9af0d6747ca5a',
    'original/N00_ZERO/run/printer.dat': '1a18f96077ee6f0203534519b389ae2bb58ac017adbf9ac2778f80f61275ebc2',
    'original/N00_ZERO/run/screen.png': '0a37aadc1f99a24bec55fa7ede2ab9201d3d3a5205fc9f0196663b55172814b1',
    'original/N01_MINUS1/capture.json': '23db41a36204b348e93cbb3fb10fe429a1c700ea31bce83a44114a5eb938ad53',
    'original/N01_MINUS1/list/caprice.log': '7452bc54b6b6c3ee7bb14641d411bda37e82c647319042967d48c7bb7e2fbd45',
    'original/N01_MINUS1/list/printer.dat': '36f2139c32622433c5d36527e63443832ed1a39d4e2eebbac1227f5d6f938de2',
    'original/N01_MINUS1/list/screen.png': '271d4d8241b7e3df04e5cf59fc7916da306e357fac416825f6fa3b6bb2c7ad4d',
    'original/N01_MINUS1/program.bin': 'e6073c21ff7e792422715640752f384192f08bbcd9f1ffc62365deea0e7962be',
    'original/N01_MINUS1/run/caprice.log': '8641121692a6eb6831ee7bcc158391dc1871e57528683b96d929da04ddaf53d7',
    'original/N01_MINUS1/run/printer.dat': '69057f071b6d9876f7221840a020a9ac06c4457f6f76ded4b35b09a13f193318',
    'original/N01_MINUS1/run/screen.png': '3b6482917666d8787dfd648692924be25756c9991f73d5423dc6730680b91c98',
    'original/N02_POS/capture.json': 'bee3c01c7a83ffd62a79673ad3b40ab26c80a1ddfb0a7ae01750bcce9d4e64ab',
    'original/N02_POS/list/caprice.log': '845c8c8ede74be10eb33cd5f6ed3b367f6fa7fca63b194d939d532b4ff48a369',
    'original/N02_POS/list/printer.dat': 'd5de86889520cf0aedda1f24d86f75dbee8465b679c6afa957ab9f52728aa4d4',
    'original/N02_POS/list/screen.png': '43674175b937c4085c902163c6214d575da39fb9078fde1198bbcb9ab57b0cf2',
    'original/N02_POS/program.bin': '72cf685ea06f674df793e8dcdac40ac8c323be48d72f8eac0d358687ba99bd88',
    'original/N02_POS/run/caprice.log': '4637f9304557dda3723416b83d54d5ee7360698a5ebb69eb29a6f17dbd2f15df',
    'original/N02_POS/run/printer.dat': '2f3f1368cd3bf8ea78b0d96f96eca27ad7237c2982104acb483a138e7a74d760',
    'original/N02_POS/run/screen.png': 'bd4017ab1d4f7ca4a523af126e291426ee26e2c108b2a75df547409342a6c70d',
    'original/N03_MIN/capture.json': '3bc1b21e079499e9c85417328fefbf8c395278c29ac810050f7f9fdeb58e14e9',
    'original/N03_MIN/list/caprice.log': 'c4949be422aedce63823323e9085bc88bbacaa3c28e9a60ff1cdc36b9e98080b',
    'original/N03_MIN/list/printer.dat': '2f03a359841a91271dd28b8ee9cd5c9c71e69e9f8e3b4a1573a061b07e44830a',
    'original/N03_MIN/list/screen.png': '35bb38b2e8cb5bd6fe130c5c4bf8f3c09f6b321fb16bb2f49331135b4fd318ca',
    'original/N03_MIN/program.bin': '14be9aaa42b40b43797d165cc6b3f62b4f535f3d40794e8dc6eed72955b2b7e6',
    'original/N03_MIN/run/caprice.log': 'bc0d7ef4fc71bec0820c756d2ff2bfb2a95f3e0561b64f9b34be09077ad2e05c',
    'original/N03_MIN/run/printer.dat': '4b027cb7784cd8d9b9d5721ea59affc4c839072e7f4978c3bec06b95a191ea19',
    'original/N03_MIN/run/screen.png': 'fa7d66595883d9ee9490002e76c2707a3f15769f0c23fefd174c166cc8b48d2d',
    'original/O00_ZERO/capture.json': '88c65eac0056fcc5cacdb780a11550b69de495b65514dec28db81342d0f128bc',
    'original/O00_ZERO/list/caprice.log': '3fd8670a8f44138064946639347f9832cca25c742fb7541c09e6ab0e6411cd7f',
    'original/O00_ZERO/list/printer.dat': 'dce4176137200b1543f74978073e84aaad270115e086481e6d46dae2ec638d16',
    'original/O00_ZERO/list/screen.png': 'b84d00bf0059027423c2f526e87c5458718ca2f3aae0367bc9b5ba3aafd5e3a4',
    'original/O00_ZERO/program.bin': 'fa78ad207e4d67c98059d6062fa60c1f135205b090d75e334460c6896439153f',
    'original/O00_ZERO/run/caprice.log': 'a7acc03a22ec7547619178fa3c20b8eb6f729be9cdd0248a8fe33dabff8cff6a',
    'original/O00_ZERO/run/printer.dat': '7003158db4c2dee2b4db6e63f325bf525c3933264c02e2257e43842963f0da7c',
    'original/O00_ZERO/run/screen.png': '6df11e78bb0a7efc6242a08452542f0c4d3976cc16b559af3c39b8cced0a3148',
    'original/O01_POS/capture.json': '3149a392cde589723f90d5f43959a3c7c71766efd15b9f341d6b9f2b247f608b',
    'original/O01_POS/list/caprice.log': '405d9ab05ca368250f2ef92288131bc74f558e9b127e4084b2560de477933b03',
    'original/O01_POS/list/printer.dat': '0e267d95afae04fdffcb6e3e307dcffacbd4c125cac5e7e6ac368d6f7c00f648',
    'original/O01_POS/list/screen.png': '4b2722817a09d0a559011a6fcb333fd57de32794c76036059988e820038f489a',
    'original/O01_POS/program.bin': '448e7c8c2043e5f6a994c82c88a50ca09c2a9edce06196fdd31a4e6c541204f7',
    'original/O01_POS/run/caprice.log': '5721671dd2c49abba7494fc8658a1d009054adfbb640081154e05cba97d06b49',
    'original/O01_POS/run/printer.dat': 'f5014577d11b38fd7ffd22adcd8bd29abdc5e0b20974519ef6e5c555e05896e1',
    'original/O01_POS/run/screen.png': '309d8cad0c25f83d86ff45794c8cf36f71d7a25fa209a81983f6d85be145b87f',
    'original/O02_NEG/capture.json': '1131e488bdd883cafbd5b0519a8ed09124604085da94405474204f1abd9b50db',
    'original/O02_NEG/list/caprice.log': '2eef7d55dd55f97932bef4f2ea3b8c16874f6bbe5131c384e93d1639460b3bce',
    'original/O02_NEG/list/printer.dat': 'dd5e26da9bdb6385dcea2e5b0a1a931adbb75d7178e53c2a0584373928167043',
    'original/O02_NEG/list/screen.png': 'a0a5c3ee46f7412d8fbfcaf980f2bdec2c522734df2896df251155600ce9d272',
    'original/O02_NEG/program.bin': '0929ca9684e73bfa06a7ea6d022967a56507af626341b08b44e979068e787136',
    'original/O02_NEG/run/caprice.log': '0d8700a9a88f1415761ce5dab2982200cd4c4f24944e46c36d15607a062fa9c5',
    'original/O02_NEG/run/printer.dat': '4b827abeba6d6564eb3e4f3c2c23acd003d0a1f0dfc282c72899f4937a824479',
    'original/O02_NEG/run/screen.png': '93210baea2dc7b667225185d99cd93cb13b2124fa7d4914056f3b64cfe67ba46',
    'original/P01_ADD/capture.json': 'bd276a9144f6b778dddb5b218e23015bc20847990636248005e0057284139b96',
    'original/P01_ADD/list/caprice.log': '20a27227d5be0c7e1dc32511c3364493ad7de521a2f58e773a8bf97e1780d9a2',
    'original/P01_ADD/list/printer.dat': 'cc23756067568db4a94c39c23ab413359876130271881fc59ddfb49f9befe6ea',
    'original/P01_ADD/list/screen.png': '33f004ea5f48783cb86f217a0124aab74db9e77e90d25ad1d1e869e330dcadbe',
    'original/P01_ADD/program.bin': '35e42b3dda23642fc5f50f7ba1c8e7b9092aa791a2eeb651742f6734f5380114',
    'original/P01_ADD/run/caprice.log': '92ca7bebb69113d4f4a9250938d5c8597c2f6a946c40f49813d7249e756e8232',
    'original/P01_ADD/run/printer.dat': 'd3357d92668c45a8cc5f5ef79ebb233a1385b4d8e530780e7c9f63e43103040a',
    'original/P01_ADD/run/screen.png': 'f71c244361d053f6aa56066085b06b00ccfbb59f4cf079c5e23574e9fdb4edf4',
    'original/P02_MULT/capture.json': '6f413140c8b5b70618eb2cf579714a6bcac3e84eadb7ca9c7db1f6ef84759a97',
    'original/P02_MULT/list/caprice.log': '4e2bc0e39e02f05e12c14466252198226b135dd83796adefb9c382555f339baa',
    'original/P02_MULT/list/printer.dat': '1a3adc1125aeb3d63db9265099591bde7245cedf71d1fe5b248b5460c9b57c4d',
    'original/P02_MULT/list/screen.png': '381185874c92279b89d4a761553842e447977385c7d15caf00a1224a556ad1be',
    'original/P02_MULT/program.bin': '6673f06e1c4627c089ef7ebad9ea0e7ae60075162024fd77c4d281cc778324c4',
    'original/P02_MULT/run/caprice.log': 'eac465c5064d3c5964df19c442fdd98efc73cb6f70cb2578096e5365c20986a9',
    'original/P02_MULT/run/printer.dat': '9c2f160f88209785657e554ab90887cecdda89fb934f1ceff6c360ceddb68c14',
    'original/P02_MULT/run/screen.png': '97f56e56e331ba9a18255d0297291eb550fe594a5dc310ef8f71b7f66d36ceac',
    'original/P03_IDIV/capture.json': '17e83775090e9ccf03cf7e1fc716793a00f071d3f05eecc4db992eb27cf0d963',
    'original/P03_IDIV/list/caprice.log': '4e0b3a8f5af47329c7f2daf71d7ca7953ed0491441e539afa7d3f60d00d956a2',
    'original/P03_IDIV/list/printer.dat': '7c2118631a2f900f764ae7da9d6e8bce08c949efdb59d67bb620c76154ed936f',
    'original/P03_IDIV/list/screen.png': '2193be2239315f2a8cf71d4b95d872f59537284e4c96c2be5665d856d9ad6af4',
    'original/P03_IDIV/program.bin': 'ac0f25e1f7b6546b97ff3a75a0eb693b49ab23ce9a977bacfcd4ca18c009d22d',
    'original/P03_IDIV/run/caprice.log': 'eabf6e86835390a6a01a46ab86d504ad5560888ec9d3e5a88c8eba8346422a61',
    'original/P03_IDIV/run/printer.dat': 'de3da0d25a6701649d1da967617f5ac81dc0c5e96e7a3158a935032924854ea1',
    'original/P03_IDIV/run/screen.png': '1a58a1dd0cb98042173330ca2e738e802880c76f54c15931cdc9b6b89424a53c',
    'original/P04_MOD/capture.json': 'c0fc9bdc966e208188f517a1b32d1ffafb78f93ecab141db17d1b5c64ca45e86',
    'original/P04_MOD/list/caprice.log': '7698a9432cb6c00f947af0027b4d8c6970430ec102fc01b3565dacbb3d69fdcc',
    'original/P04_MOD/list/printer.dat': '4371a832c76f7092376c12d7e247f609a7e587b0b01e3cfb2a35bdab8c78f047',
    'original/P04_MOD/list/screen.png': '876adc338d13c8d5679e3c0d22dcceccc3a6e6496f0bf4e50a35e302e452c094',
    'original/P04_MOD/program.bin': '6e8570f61d3d1ee316ee5071e7f6854f0a170b3c18e5a71a7f0feeddf6394200',
    'original/P04_MOD/run/caprice.log': '98c820f945855fb2be4fac92f8f4f2c9781dbe754db2be24d90645f515c84635',
    'original/P04_MOD/run/printer.dat': '788d351afad5407d5280aaaf1b6d8c1e21789af0dd45de5370dc19a31a9b2b1a',
    'original/P04_MOD/run/screen.png': '6d24a114472699ea348ad8674d9e99199f8f89c6ce3c6192be7f1e2fd86e1584',
    'original/P05_REL/capture.json': '3efe91284c240a86109bd33cf0c0297f6b250791e32e22adce45f99e37715e05',
    'original/P05_REL/list/caprice.log': '8dfb668b4334c903c383fbf98bd08a1e3a2d770875ab75668c1ae22af0304eec',
    'original/P05_REL/list/printer.dat': '4861489a47fa140ba479bd558c8b3f763519cfa83d46309d3de623ec37d72a12',
    'original/P05_REL/list/screen.png': '560c9adf58732d3ca714be448a2f61d53a97a23242dbafb5cefd57dc4e0a073e',
    'original/P05_REL/program.bin': 'e06ebc527d82d310cdb78de6782a194b3f58b27891b422c0f3ba03ed2ea84e2f',
    'original/P05_REL/run/caprice.log': '55d474ace58f64d33fec7afa0c7574c0b26b3798f5fff72d0b81bc7b59ac0a44',
    'original/P05_REL/run/printer.dat': '5b107e5adeeb5d3a2eb430c40225bb259dd4f7f7e45006019cc10293de34aa22',
    'original/P05_REL/run/screen.png': 'd0c92d8826a1f824d675dfc822d4d048709db89decb064cd17f12b886ab58b9d',
    'original/P06_IF_ELSE/capture.json': 'a3a14284902a01d8d02aa9d0959ac05e49a7eb312eff28885c41a4f0f7cc1781',
    'original/P06_IF_ELSE/list/caprice.log': '29616e9d021558da873dcffdafbf4ed6245994b4470f2f4ee570ab33103b18b7',
    'original/P06_IF_ELSE/list/printer.dat': '8c145d084e72371942ba14283d95f6cdaffcee71198f331440f1af0b195d4172',
    'original/P06_IF_ELSE/list/screen.png': '22bd23745b00723d796a088ee7a79017d189f47027dabbbc5632b0ecdf8dc02d',
    'original/P06_IF_ELSE/program.bin': '656ecd4587e967a57cbc44fe303705e7f944081084e4c745ec75ba7ee29f4b8d',
    'original/P06_IF_ELSE/run/caprice.log': 'ea6b8ce53f102f1029d759d941995aed7e0913270c2e66786ffc6b8bbf859eae',
    'original/P06_IF_ELSE/run/printer.dat': '5071a0b2593efa3942fc13893d7d33d4bbede10c2aa07d18d3376fcd9068b7da',
    'original/P06_IF_ELSE/run/screen.png': '9a60269f25b25af6b31622b492c0572b2ccb903191f352f81b297e7bcab79c07',
    'original/P07_NESTED/capture.json': 'bdaee928bd6b115139279855cc37dec92fa42b3fa5cd209985d841841d1bc5b0',
    'original/P07_NESTED/list/caprice.log': 'dd77c285fe1fe1a1949a27c2039b821edd16aec0d17685001294064bf9e25ea1',
    'original/P07_NESTED/list/printer.dat': '9678577be9ddc9ba413cf0e467f0b8391690665bcb5bc2a97d1bb57840d4b9e1',
    'original/P07_NESTED/list/screen.png': 'd56b244ce79c100629c0dee719499797c6ed063185d43842c07a6e4ca41beb57',
    'original/P07_NESTED/program.bin': '3bc0bf6a0eb6f9a66b79e9f6d4c21528c5efc91b7db1a5f1bcbbe6d6711a5bd6',
    'original/P07_NESTED/run/caprice.log': '6c44740ac53fde4e07bf82b6dfbf7fa02b972f8ea57c92956afcedc6d909b463',
    'original/P07_NESTED/run/printer.dat': 'f5b96d57d7b04c6bcfede4d110cd399142ad334c79f59cd3d5f276756564806d',
    'original/P07_NESTED/run/screen.png': '52f49c1181915eee3e337bc12d933bb663fb3a4da8281e5f3c9749387bece00c',
    'original/P08_UNARY/capture.json': 'd9e3ed362986ada56d5aab5d27c9758d81e97a1890ba27d44eb004809d476969',
    'original/P08_UNARY/list/caprice.log': '61c6a859cd58fec663f991c80c8ff33fd9d49567213a38048d6ce9c84d6b622f',
    'original/P08_UNARY/list/printer.dat': '5421f65722bd39a646829a5158c7a8d56b55b3294bd5f30d982b374ebd0266c6',
    'original/P08_UNARY/list/screen.png': '4e24c562243097e841405cc2adcb49b387f0adb5ec039619de8271db1132e078',
    'original/P08_UNARY/program.bin': '656d1f31230f823ccccbe484fa3a16505b52f2f79c765cb39d0db3c179d05f71',
    'original/P08_UNARY/run/caprice.log': '1149e5adb41cfde48da28ee87dd081efa258497211952154c71b3b3ba6480f3c',
    'original/P08_UNARY/run/printer.dat': 'ca4883f318a0c1b1fa69bad75182546aaca5709a39b65ee15813178edfda8b98',
    'original/P08_UNARY/run/screen.png': '7d766a31c95825280b9ac1187f2ef73a08bd66709bb268326ff3b1e3884fb0c5',
    'original/X00_ZERO/capture.json': '0c9a1d433f34b4dfe3baf7b40a7c2155cdc28e7fe5a76d8335b224f944205d85',
    'original/X00_ZERO/list/caprice.log': '4fac9a6ef500776d4bd1ac8bb4b229f8b4ec6d808f3667092c430b4b82ce722b',
    'original/X00_ZERO/list/printer.dat': '5638a8fba1e23fba1570142167479c2fbe044a781ffc529d3829841d1b3d6ce1',
    'original/X00_ZERO/list/screen.png': '5840ca9ce092d79cd747b827002a3d9aa1f8699024312794f3472d5e0f32138a',
    'original/X00_ZERO/program.bin': '8eeaf2d38d3ec67d48621bc5ae07fa3f58667c87eb7b32d40251304ab3f6f190',
    'original/X00_ZERO/run/caprice.log': 'd3c8d01033cd00ef972a26d1c6825a3223675e3e5b07691305deff3f52671093',
    'original/X00_ZERO/run/printer.dat': 'd3c18c696c2ebaf42f23451929602c3e53c78efe6106bc36031c1e0bb44f37f3',
    'original/X00_ZERO/run/screen.png': '28eead583cb131cb04c5e3a4808306a1eb968a469294bf4a87851e266ddf4986',
    'original/X01_POS/capture.json': 'e9c95956941a192c54b92f825c06431a4aee7782b68441cca9b04f5356777273',
    'original/X01_POS/list/caprice.log': '7d53d32e74b96f76c1983c741a35422ae5d3927a175d2f9b9aa0402e3105a861',
    'original/X01_POS/list/printer.dat': '2f58b8a79987586183ddc619dd4892f80eedcaf99642385926651ca334e53383',
    'original/X01_POS/list/screen.png': '3dc95499533364358e5c1001fadfca29b27b395e9889ab6ae16b64a0880bcca6',
    'original/X01_POS/program.bin': '100d04fcfd0cd36162eb8398ef24b852f30eee223edbbafc140982a57c262589',
    'original/X01_POS/run/caprice.log': 'abf4b709f61a2c69b7944f023921976eb4542ca351848052c729a557f008326d',
    'original/X01_POS/run/printer.dat': '500038a37d1be23d7db4efed10674acb5c1d94094c9cf0bf11a22d563f3a9217',
    'original/X01_POS/run/screen.png': 'ef1fa58206fcfebec3c33d0c8262908cd4ba0a9537e1a357dd97576d1e1e1272',
    'original/X02_NEG/capture.json': 'd5fe2799774e1928f542aae948e8d23ce904cfee7993a5ee7f247b05fc1293df',
    'original/X02_NEG/list/caprice.log': '2942c5180a4da9e76f413d28bd13708df0f04ec52cc3e18469a764115dda1406',
    'original/X02_NEG/list/printer.dat': '2b2d428e8300886036a1d406ca7f2ec4be108bc4abeeec51e9a221cdf033fd08',
    'original/X02_NEG/list/screen.png': 'a08591b05274ad585d18cbe9a678c5e3a56b6c673320d185372e5696f70789ec',
    'original/X02_NEG/program.bin': 'f21bbb94f9f8c2eb3df1321b2f15f5a9863adcca61a94670cc4ad3b51ebfd6d3',
    'original/X02_NEG/run/caprice.log': 'aa94bb8385a69281263b7ed589cf27f1839e81c437a1962883b0f92b8ecad886',
    'original/X02_NEG/run/printer.dat': '462d40b148cee1d5333282ab85e326ab458fbe604cd36a79cdbbb6a9daeae63c',
    'original/X02_NEG/run/screen.png': 'cd03b4b5561ccbce87456086b3c2a08c26c03e8b7e637aff32ed72ba364ac22a',
    'repeat/A00_ZERO/capture.json': 'f7e2da9f28b2ac0fc18c6b9372407222639d19f35e8d3900de6817a876e19ff8',
    'repeat/A00_ZERO/list/caprice.log': '5f3d0288d9fa142c2429055af7dab240b9aac2066485176d2f5e08f3c2377398',
    'repeat/A00_ZERO/list/printer.dat': '97b14bb79fba58a325e821f77ac07de7c3be60c53f2f0edd7f8d10eb00a26098',
    'repeat/A00_ZERO/list/screen.png': '2c9de5255930c80898a9158f21610d2198c8f5681c860e459e3bcb057232e0d8',
    'repeat/A00_ZERO/program.bin': '76735dab385e1bd27e6112d1e38944c688a652e8901c5172146079462ee185fc',
    'repeat/A00_ZERO/run/caprice.log': '2b4f4efa82cb46d7cfd61bb920df53dc6dede80738443c6a51d2c295364b31b2',
    'repeat/A00_ZERO/run/printer.dat': 'dd92699746263fd7c9cf2b5c6d020c7db3917497b084609039d05437439f23ff',
    'repeat/A00_ZERO/run/screen.png': '8e68092a0f1aad48046c438c0e4066f7c4cdea064d0ee069a2eb26950a4b47c1',
    'repeat/A01_POS/capture.json': '8adbc85b06ff6e114d8de61bd335a3102f417c2b0a6f48293421ca78c8ccde47',
    'repeat/A01_POS/list/caprice.log': '3d7a69563c33a340d918ed331317a7f4b950f5428222a0ec47857f70adaea307',
    'repeat/A01_POS/list/printer.dat': '5dc9cb6cfef95cab817a4a23f7feafd7a6150373ad462123b6f4bf1dba84c3c2',
    'repeat/A01_POS/list/screen.png': 'd255758f703e3c417b51347106d65d1f4541042cd49b9355ace9eae40dba9728',
    'repeat/A01_POS/program.bin': '73ab37e8a0575d292944eb50c9ca79ad9a1e1fb98cf0fbdf5424f299666070ea',
    'repeat/A01_POS/run/caprice.log': 'bd7b0c7e1f4e879fa50e46bef8554671f18234afe1377e22b4d7c2d0db70ec98',
    'repeat/A01_POS/run/printer.dat': 'd0e142521557aa895fb5bf7650810513919d0e81f8b46e1757e288d0f9ce1fad',
    'repeat/A01_POS/run/screen.png': 'e7c59510b3029f67f6c10df6e9de45f1242eea8cafb44c0bde1dd2466688f991',
    'repeat/A02_NEG/capture.json': '902e88cdebe7b2d823eacbc1c7b4056a07c9c084515e3a387a8cd1694e10fbd2',
    'repeat/A02_NEG/list/caprice.log': '1a9ca48233fdbfa066d9276f6178665d5ad3128cc99e2a5930cb39e4b8a0380b',
    'repeat/A02_NEG/list/printer.dat': '14afba5b0afacbd9be2b79c653af0d7491b6ae20daef5d20a40a100d49f787db',
    'repeat/A02_NEG/list/screen.png': '27e30a7ed1648720e8e574f5de9ca715b8a512325ce8912a92b12a17849a3954',
    'repeat/A02_NEG/program.bin': '212bfdcf7bd2b743b68bd2e648d325cf2437ea8d632422da787053aaad014af9',
    'repeat/A02_NEG/run/caprice.log': 'b07ab6915aa263ded89e251a94430cc4682567ebb4ed81e2c4401a177ae4b1a1',
    'repeat/A02_NEG/run/printer.dat': '22e01b30dfcc20e32a4db2de817e882354dd0743ba0ed44b0248595af4c74f0c',
    'repeat/A02_NEG/run/screen.png': '0f64ef25ec5e61f0644b671941621c1b1c96cd1683b354af19bb0c447ef597a1',
    'repeat/A03_MIN/capture.json': '54b0feece45830ea3a92a142c037ca0acb0495176b2987ca78699cdeb790a444',
    'repeat/A03_MIN/list/caprice.log': 'e9a3fc6e2e3e0eaf44bcc3440c928f95f3fa99dbed588262ed18f64d7111a7b0',
    'repeat/A03_MIN/list/printer.dat': '90b967e04bd093616e04e9b81976e342d08e75804bc8cfda04d299dfd1141c6a',
    'repeat/A03_MIN/list/screen.png': '467684b48edccf3786088b4fd250c3209abd35e1ae5ea07132e4213601f1b5ad',
    'repeat/A03_MIN/program.bin': 'ce7da9cbf5fc15c79b3b86bec29a248d53c4f3e2a3c776d5c1f528c68d121b06',
    'repeat/A03_MIN/run/caprice.log': '89ccd4e1ed3c617dff8a1bc0655288d3e543f638f07bdc1a73b3ff92f2bbf177',
    'repeat/A03_MIN/run/printer.dat': '854ec3b4b75c35ae40f8cb9c21fdb12eda247c3e22e6a7a09d3eac005746b0a5',
    'repeat/A03_MIN/run/screen.png': 'a1562c9927104c5e7732d6a6dc62e46533d85ef29dbd937bc07fdeddccd74a86',
    'repeat/E01_DIV0/capture.json': 'def3e2651d8050fd549f533e1f31042c93a2a340bf3b2cfc10f41e0aadaa8056',
    'repeat/E01_DIV0/list/caprice.log': 'd6674891a79a03aa6ee55565eca081d7b7f42b717b0fd21642959ee5b1ab313c',
    'repeat/E01_DIV0/list/printer.dat': '74b0182803a4f188f503b1eb5a0461a4a6be713306873a2eb752496d027e86ab',
    'repeat/E01_DIV0/list/screen.png': 'a82aeb110fed709f5285270baa94dd988db137bf970e0a6a5821a0d28075bbf8',
    'repeat/E01_DIV0/program.bin': 'f0b991ac09e42d286417082f27e14fb64ed16d2fa794d6a98cb98c60e68646b4',
    'repeat/E01_DIV0/run/caprice.log': 'f541adae7a6309acdb1e9c970e426d44ba4f3709156ffd1b16f4364d51163047',
    'repeat/E01_DIV0/run/printer.dat': 'adde6b118bc50f80858dcc271812f24829cc74edb6633fa0566b11f6e33bbcfd',
    'repeat/E01_DIV0/run/screen.png': '681596a95b1a7c3c88bab885dca64287ed220858a77a8dc52448a1ca3047ede0',
    'repeat/E02_OVERFLOW/capture.json': 'd48ce392eb208c00fa2c7ec6a48ef9478b1aa61575b8fc2676e98c05bed6c83b',
    'repeat/E02_OVERFLOW/list/caprice.log': 'bbcad1dfc4805f3cce673361e2379239476197b178ed255ed38550a579a4223c',
    'repeat/E02_OVERFLOW/list/printer.dat': '1239cfb823bfb7fb72fb145e2be7270ecda4d547f2d9e8b1b510038545ea1e34',
    'repeat/E02_OVERFLOW/list/screen.png': '55c6b28143dd3f6cf4679a1f341f422566d5efe38e33394a9442f72613618959',
    'repeat/E02_OVERFLOW/program.bin': '6b6cf3a0dcd32ad76a85b131c4cc4f71c12789d532953d60a164fb944a0e6601',
    'repeat/E02_OVERFLOW/run/caprice.log': '4a3b9b4be51ac88cd0eb2c98c7e457de9750c6f71bb161e04cf74d90673e2ea2',
    'repeat/E02_OVERFLOW/run/printer.dat': 'f682061d9f57dffd070c22a03903840f8692a4ef82770287c9c33e740522d3e4',
    'repeat/E02_OVERFLOW/run/screen.png': '2183b0561cfb8ec6b21e761b37ffcc22b0eff4bb2af21642c708696b413056ea',
    'repeat/N00_ZERO/capture.json': 'd5a3b87bc4915b585073f729fa02a4901e38e8e6e387a5679afd79d5808e2e1b',
    'repeat/N00_ZERO/list/caprice.log': 'c44acb1674a53b3ed3a627081d7f727c521ea14195984fb85005fb5b3e0909a1',
    'repeat/N00_ZERO/list/printer.dat': 'dd026bb695b84f8a56c47284233c517517609e6bcaf34083c354ef64507c29b5',
    'repeat/N00_ZERO/list/screen.png': '0c7ac44eeff50977c47ccbf1ba0059ecec545311675432849a1c7bac2dcd72c8',
    'repeat/N00_ZERO/program.bin': '55c557fcadc2b76d2a758ada4679dcdc3e4ac31e70441fa9fe1f07f8fdb236a6',
    'repeat/N00_ZERO/run/caprice.log': 'b3cd78d398243e87bef48242b26a0c7f91c3d790d1f3ee4b7155ea0350d55f31',
    'repeat/N00_ZERO/run/printer.dat': '1a18f96077ee6f0203534519b389ae2bb58ac017adbf9ac2778f80f61275ebc2',
    'repeat/N00_ZERO/run/screen.png': '0a37aadc1f99a24bec55fa7ede2ab9201d3d3a5205fc9f0196663b55172814b1',
    'repeat/N01_MINUS1/capture.json': '55a1ba7c56b6f0b130123c6c246b83f96c05a483df833c67c6858d585c54c887',
    'repeat/N01_MINUS1/list/caprice.log': '3377b61eca125cb8d1e044b1f1525415223ae3a31a04c12fe6c3edaa2f2b35c3',
    'repeat/N01_MINUS1/list/printer.dat': '36f2139c32622433c5d36527e63443832ed1a39d4e2eebbac1227f5d6f938de2',
    'repeat/N01_MINUS1/list/screen.png': '271d4d8241b7e3df04e5cf59fc7916da306e357fac416825f6fa3b6bb2c7ad4d',
    'repeat/N01_MINUS1/program.bin': 'e6073c21ff7e792422715640752f384192f08bbcd9f1ffc62365deea0e7962be',
    'repeat/N01_MINUS1/run/caprice.log': 'f12997a6ade602c8b3e78368edfb2c98fd8ca860bb1ee6deae2f1ed1614aca21',
    'repeat/N01_MINUS1/run/printer.dat': '69057f071b6d9876f7221840a020a9ac06c4457f6f76ded4b35b09a13f193318',
    'repeat/N01_MINUS1/run/screen.png': '3b6482917666d8787dfd648692924be25756c9991f73d5423dc6730680b91c98',
    'repeat/N02_POS/capture.json': 'e5223db458613ff60ef212622d319b59e798ebf23b62a47191395261d1f09068',
    'repeat/N02_POS/list/caprice.log': '49ace01f1a51412a8ed91ca3d1fd4296e9dadf285ed32fb920b876fdbe229459',
    'repeat/N02_POS/list/printer.dat': 'd5de86889520cf0aedda1f24d86f75dbee8465b679c6afa957ab9f52728aa4d4',
    'repeat/N02_POS/list/screen.png': '43674175b937c4085c902163c6214d575da39fb9078fde1198bbcb9ab57b0cf2',
    'repeat/N02_POS/program.bin': '72cf685ea06f674df793e8dcdac40ac8c323be48d72f8eac0d358687ba99bd88',
    'repeat/N02_POS/run/caprice.log': 'a4176d37a3845fa65d39216434b47223c837d33456ed0bcc47cb2a08f09a9bc8',
    'repeat/N02_POS/run/printer.dat': '2f3f1368cd3bf8ea78b0d96f96eca27ad7237c2982104acb483a138e7a74d760',
    'repeat/N02_POS/run/screen.png': 'bd4017ab1d4f7ca4a523af126e291426ee26e2c108b2a75df547409342a6c70d',
    'repeat/N03_MIN/capture.json': '504ec6b9d2db9b4ccff817d08353e1c225f581420a0ade2df4630c622993cc80',
    'repeat/N03_MIN/list/caprice.log': '2b8efded50bc386a98c15b7723f28f858b310e41c7a8caca81ef790e7b615e04',
    'repeat/N03_MIN/list/printer.dat': '2f03a359841a91271dd28b8ee9cd5c9c71e69e9f8e3b4a1573a061b07e44830a',
    'repeat/N03_MIN/list/screen.png': '35bb38b2e8cb5bd6fe130c5c4bf8f3c09f6b321fb16bb2f49331135b4fd318ca',
    'repeat/N03_MIN/program.bin': '14be9aaa42b40b43797d165cc6b3f62b4f535f3d40794e8dc6eed72955b2b7e6',
    'repeat/N03_MIN/run/caprice.log': 'a8f3cac025f6d6fbd5679731d362d160d9cbacf8b737fe3330aec39c75ef4b73',
    'repeat/N03_MIN/run/printer.dat': '4b027cb7784cd8d9b9d5721ea59affc4c839072e7f4978c3bec06b95a191ea19',
    'repeat/N03_MIN/run/screen.png': 'fa7d66595883d9ee9490002e76c2707a3f15769f0c23fefd174c166cc8b48d2d',
    'repeat/O00_ZERO/capture.json': '46e9204e10502b66b84c64b4f5dca24babbfd6b9d357306aedc9add72f632277',
    'repeat/O00_ZERO/list/caprice.log': '655380f1c626a27e17fe84e74e823ec0b868630af62bf614cb79190a591a7022',
    'repeat/O00_ZERO/list/printer.dat': 'dce4176137200b1543f74978073e84aaad270115e086481e6d46dae2ec638d16',
    'repeat/O00_ZERO/list/screen.png': 'b84d00bf0059027423c2f526e87c5458718ca2f3aae0367bc9b5ba3aafd5e3a4',
    'repeat/O00_ZERO/program.bin': 'fa78ad207e4d67c98059d6062fa60c1f135205b090d75e334460c6896439153f',
    'repeat/O00_ZERO/run/caprice.log': '14e403779197f9ba3b2c76c772f806690da311da6435e5eac4215a17a5d849fa',
    'repeat/O00_ZERO/run/printer.dat': '7003158db4c2dee2b4db6e63f325bf525c3933264c02e2257e43842963f0da7c',
    'repeat/O00_ZERO/run/screen.png': '6df11e78bb0a7efc6242a08452542f0c4d3976cc16b559af3c39b8cced0a3148',
    'repeat/O01_POS/capture.json': '58d2a2af08824c7e34cd9241865bfaa473fe7054530a333d4a668ed887678c84',
    'repeat/O01_POS/list/caprice.log': 'dc69ba9e749a28888b6d53bc88daf6d70388b8ba73c6fdcc03360fc26d97a9d0',
    'repeat/O01_POS/list/printer.dat': '0e267d95afae04fdffcb6e3e307dcffacbd4c125cac5e7e6ac368d6f7c00f648',
    'repeat/O01_POS/list/screen.png': '4b2722817a09d0a559011a6fcb333fd57de32794c76036059988e820038f489a',
    'repeat/O01_POS/program.bin': '448e7c8c2043e5f6a994c82c88a50ca09c2a9edce06196fdd31a4e6c541204f7',
    'repeat/O01_POS/run/caprice.log': 'c1b92248100c055acfc9df217448c93deb920f244cadaf0be5c4e52d7d5c8245',
    'repeat/O01_POS/run/printer.dat': 'f5014577d11b38fd7ffd22adcd8bd29abdc5e0b20974519ef6e5c555e05896e1',
    'repeat/O01_POS/run/screen.png': '309d8cad0c25f83d86ff45794c8cf36f71d7a25fa209a81983f6d85be145b87f',
    'repeat/O02_NEG/capture.json': '457b81c3090c683cdfe4732b678a4886d3655bd1a73c0158096030aa8026f41b',
    'repeat/O02_NEG/list/caprice.log': '3d715320a76f4afe9fa9ab8be6cdce7e66901e4be9790f473c5de3930074b4b3',
    'repeat/O02_NEG/list/printer.dat': 'dd5e26da9bdb6385dcea2e5b0a1a931adbb75d7178e53c2a0584373928167043',
    'repeat/O02_NEG/list/screen.png': 'a0a5c3ee46f7412d8fbfcaf980f2bdec2c522734df2896df251155600ce9d272',
    'repeat/O02_NEG/program.bin': '0929ca9684e73bfa06a7ea6d022967a56507af626341b08b44e979068e787136',
    'repeat/O02_NEG/run/caprice.log': '28a9a8635f50fa17f98b0e6c106cf0f3b053c2f22466c03d6af12c255bd30287',
    'repeat/O02_NEG/run/printer.dat': '4b827abeba6d6564eb3e4f3c2c23acd003d0a1f0dfc282c72899f4937a824479',
    'repeat/O02_NEG/run/screen.png': '93210baea2dc7b667225185d99cd93cb13b2124fa7d4914056f3b64cfe67ba46',
    'repeat/P01_ADD/capture.json': '5b34184742d7cd05f6304a2d96c3ae8949baec72ff4c4ca8189018e7ef03c77e',
    'repeat/P01_ADD/list/caprice.log': 'fb4f115eb78aa7d6cd5804d91b42198b994465bd2ea11b22a04043b43deea1d7',
    'repeat/P01_ADD/list/printer.dat': 'cc23756067568db4a94c39c23ab413359876130271881fc59ddfb49f9befe6ea',
    'repeat/P01_ADD/list/screen.png': '33f004ea5f48783cb86f217a0124aab74db9e77e90d25ad1d1e869e330dcadbe',
    'repeat/P01_ADD/program.bin': '35e42b3dda23642fc5f50f7ba1c8e7b9092aa791a2eeb651742f6734f5380114',
    'repeat/P01_ADD/run/caprice.log': '5b644fc888dade7cfefd5194ee1cdee50ba1f01a8c1ee64789e3e4faf442ff3e',
    'repeat/P01_ADD/run/printer.dat': 'd3357d92668c45a8cc5f5ef79ebb233a1385b4d8e530780e7c9f63e43103040a',
    'repeat/P01_ADD/run/screen.png': 'f71c244361d053f6aa56066085b06b00ccfbb59f4cf079c5e23574e9fdb4edf4',
    'repeat/P02_MULT/capture.json': 'e57b7473c2523557e34c3ada12d6516b78a320f64d04574e5f22c4dce7cd36ff',
    'repeat/P02_MULT/list/caprice.log': '305544322327cf5d94f3c77b432b89f49ddcb8e4a7c557f02117f9a73c6d96f4',
    'repeat/P02_MULT/list/printer.dat': '1a3adc1125aeb3d63db9265099591bde7245cedf71d1fe5b248b5460c9b57c4d',
    'repeat/P02_MULT/list/screen.png': '381185874c92279b89d4a761553842e447977385c7d15caf00a1224a556ad1be',
    'repeat/P02_MULT/program.bin': '6673f06e1c4627c089ef7ebad9ea0e7ae60075162024fd77c4d281cc778324c4',
    'repeat/P02_MULT/run/caprice.log': 'f6a986fd2f55b206f3e7931aa6cbc92056019a12cade44ee56e4cc5a6b4a871d',
    'repeat/P02_MULT/run/printer.dat': '9c2f160f88209785657e554ab90887cecdda89fb934f1ceff6c360ceddb68c14',
    'repeat/P02_MULT/run/screen.png': '97f56e56e331ba9a18255d0297291eb550fe594a5dc310ef8f71b7f66d36ceac',
    'repeat/P03_IDIV/capture.json': '9d4a2d76682a7a6196e0a2267ec4c2744fb6f81e461eea5ff51ab77fb14e82bb',
    'repeat/P03_IDIV/list/caprice.log': '09cd4cee2756a7184a2fc903b674d7aab25e5e5f0bca4c1a6754eca13d732641',
    'repeat/P03_IDIV/list/printer.dat': '7c2118631a2f900f764ae7da9d6e8bce08c949efdb59d67bb620c76154ed936f',
    'repeat/P03_IDIV/list/screen.png': '2193be2239315f2a8cf71d4b95d872f59537284e4c96c2be5665d856d9ad6af4',
    'repeat/P03_IDIV/program.bin': 'ac0f25e1f7b6546b97ff3a75a0eb693b49ab23ce9a977bacfcd4ca18c009d22d',
    'repeat/P03_IDIV/run/caprice.log': '4bceb004bf1dfb4815ac61351134f6fcd42958fc384ffdb08870ed58f52a8cbe',
    'repeat/P03_IDIV/run/printer.dat': 'de3da0d25a6701649d1da967617f5ac81dc0c5e96e7a3158a935032924854ea1',
    'repeat/P03_IDIV/run/screen.png': '1a58a1dd0cb98042173330ca2e738e802880c76f54c15931cdc9b6b89424a53c',
    'repeat/P04_MOD/capture.json': 'd907bd1b9d24bc649db1c2f9032161dda138ce32c43f4eb50c225827b1b6cb7c',
    'repeat/P04_MOD/list/caprice.log': 'd5339406568f0f69df5e0005aeef7b4631d67c636a3d9514fe22631b17163abb',
    'repeat/P04_MOD/list/printer.dat': '4371a832c76f7092376c12d7e247f609a7e587b0b01e3cfb2a35bdab8c78f047',
    'repeat/P04_MOD/list/screen.png': '876adc338d13c8d5679e3c0d22dcceccc3a6e6496f0bf4e50a35e302e452c094',
    'repeat/P04_MOD/program.bin': '6e8570f61d3d1ee316ee5071e7f6854f0a170b3c18e5a71a7f0feeddf6394200',
    'repeat/P04_MOD/run/caprice.log': '17162d8a9bab0f2c33246e6054b1910b9c15591874174b6588faffc65877180f',
    'repeat/P04_MOD/run/printer.dat': '788d351afad5407d5280aaaf1b6d8c1e21789af0dd45de5370dc19a31a9b2b1a',
    'repeat/P04_MOD/run/screen.png': '6d24a114472699ea348ad8674d9e99199f8f89c6ce3c6192be7f1e2fd86e1584',
    'repeat/P05_REL/capture.json': 'a3823619177296aee4e2f421387ae3a77accf2609cf5ecac570321d830b3a1c9',
    'repeat/P05_REL/list/caprice.log': '3e6ef6f33b029690641e5e1024cce7e1ad18b23ca1ee4db12eb1911c91741c95',
    'repeat/P05_REL/list/printer.dat': '4861489a47fa140ba479bd558c8b3f763519cfa83d46309d3de623ec37d72a12',
    'repeat/P05_REL/list/screen.png': '560c9adf58732d3ca714be448a2f61d53a97a23242dbafb5cefd57dc4e0a073e',
    'repeat/P05_REL/program.bin': 'e06ebc527d82d310cdb78de6782a194b3f58b27891b422c0f3ba03ed2ea84e2f',
    'repeat/P05_REL/run/caprice.log': 'd9922e6687321eeaeecd77e9000048b686d7e58886c04b1dfca47cdb4758a287',
    'repeat/P05_REL/run/printer.dat': '5b107e5adeeb5d3a2eb430c40225bb259dd4f7f7e45006019cc10293de34aa22',
    'repeat/P05_REL/run/screen.png': 'd0c92d8826a1f824d675dfc822d4d048709db89decb064cd17f12b886ab58b9d',
    'repeat/P06_IF_ELSE/capture.json': '6ea5d20bfa6079dea74c347ba4e0d87174f16b3deabda08437bf5be5dd696905',
    'repeat/P06_IF_ELSE/list/caprice.log': '4579983f9f1aa4108f637bd2904af6196c0ac9ff3d665d111f9027eee8a56390',
    'repeat/P06_IF_ELSE/list/printer.dat': '8c145d084e72371942ba14283d95f6cdaffcee71198f331440f1af0b195d4172',
    'repeat/P06_IF_ELSE/list/screen.png': '22bd23745b00723d796a088ee7a79017d189f47027dabbbc5632b0ecdf8dc02d',
    'repeat/P06_IF_ELSE/program.bin': '656ecd4587e967a57cbc44fe303705e7f944081084e4c745ec75ba7ee29f4b8d',
    'repeat/P06_IF_ELSE/run/caprice.log': '1aadc3227f7b779f1a63b1b89cf697da46b3a58570448ebe46e7f69e57a0899e',
    'repeat/P06_IF_ELSE/run/printer.dat': '5071a0b2593efa3942fc13893d7d33d4bbede10c2aa07d18d3376fcd9068b7da',
    'repeat/P06_IF_ELSE/run/screen.png': '9a60269f25b25af6b31622b492c0572b2ccb903191f352f81b297e7bcab79c07',
    'repeat/P07_NESTED/capture.json': '4d84d6f9d6318a96e88d6c313a36d7bdc5c309f9f32a989c4f839d03071af1cb',
    'repeat/P07_NESTED/list/caprice.log': '46bd66f94ec4f7278a8ffab28452a849d0899736029644abc7f2f13adb859a47',
    'repeat/P07_NESTED/list/printer.dat': '9678577be9ddc9ba413cf0e467f0b8391690665bcb5bc2a97d1bb57840d4b9e1',
    'repeat/P07_NESTED/list/screen.png': 'd56b244ce79c100629c0dee719499797c6ed063185d43842c07a6e4ca41beb57',
    'repeat/P07_NESTED/program.bin': '3bc0bf6a0eb6f9a66b79e9f6d4c21528c5efc91b7db1a5f1bcbbe6d6711a5bd6',
    'repeat/P07_NESTED/run/caprice.log': 'b68201851692f1f0de7b0197136d60c1de442e09d369a70f4158e9ab4f01a81f',
    'repeat/P07_NESTED/run/printer.dat': 'f5b96d57d7b04c6bcfede4d110cd399142ad334c79f59cd3d5f276756564806d',
    'repeat/P07_NESTED/run/screen.png': '52f49c1181915eee3e337bc12d933bb663fb3a4da8281e5f3c9749387bece00c',
    'repeat/P08_UNARY/capture.json': '05a3f8c1a5224f466a4fc848bb7294c6d8294a948301c43ef9755e8358822247',
    'repeat/P08_UNARY/list/caprice.log': '7a58a3f12336e96ffc03fe00c1eed18080c6d550e580fb6157376234c01cf1e3',
    'repeat/P08_UNARY/list/printer.dat': '5421f65722bd39a646829a5158c7a8d56b55b3294bd5f30d982b374ebd0266c6',
    'repeat/P08_UNARY/list/screen.png': '4e24c562243097e841405cc2adcb49b387f0adb5ec039619de8271db1132e078',
    'repeat/P08_UNARY/program.bin': '656d1f31230f823ccccbe484fa3a16505b52f2f79c765cb39d0db3c179d05f71',
    'repeat/P08_UNARY/run/caprice.log': '6b0259061688114647b99eaa0d9564d13ea7017235cbb01aa57ce7f25cb2e900',
    'repeat/P08_UNARY/run/printer.dat': 'ca4883f318a0c1b1fa69bad75182546aaca5709a39b65ee15813178edfda8b98',
    'repeat/P08_UNARY/run/screen.png': '7d766a31c95825280b9ac1187f2ef73a08bd66709bb268326ff3b1e3884fb0c5',
    'repeat/X00_ZERO/capture.json': '0da6eb6a7aeb614a272e58b6da7994018da94fc17c6c6a66bf0f7e445c0d22f8',
    'repeat/X00_ZERO/list/caprice.log': 'eaefd770db1c6bd12c4d154dd434ace2f1d04736b900af572542c86d5e177be8',
    'repeat/X00_ZERO/list/printer.dat': '5638a8fba1e23fba1570142167479c2fbe044a781ffc529d3829841d1b3d6ce1',
    'repeat/X00_ZERO/list/screen.png': '5840ca9ce092d79cd747b827002a3d9aa1f8699024312794f3472d5e0f32138a',
    'repeat/X00_ZERO/program.bin': '8eeaf2d38d3ec67d48621bc5ae07fa3f58667c87eb7b32d40251304ab3f6f190',
    'repeat/X00_ZERO/run/caprice.log': 'edeb5a0f3bfc03ce7341e0fd2ef27d0b855cfbe7d6d444ffe95d579d7cb61e7c',
    'repeat/X00_ZERO/run/printer.dat': 'd3c18c696c2ebaf42f23451929602c3e53c78efe6106bc36031c1e0bb44f37f3',
    'repeat/X00_ZERO/run/screen.png': '28eead583cb131cb04c5e3a4808306a1eb968a469294bf4a87851e266ddf4986',
    'repeat/X01_POS/capture.json': '27be9bfcb8bb485156f41fba716e132a8fff0617de7d0822da5edcb79ac3fbae',
    'repeat/X01_POS/list/caprice.log': '9af23b552fd79109925a28b6fff7c989e2ff18b7ef19c1ed87f9534849af5405',
    'repeat/X01_POS/list/printer.dat': '2f58b8a79987586183ddc619dd4892f80eedcaf99642385926651ca334e53383',
    'repeat/X01_POS/list/screen.png': '3dc95499533364358e5c1001fadfca29b27b395e9889ab6ae16b64a0880bcca6',
    'repeat/X01_POS/program.bin': '100d04fcfd0cd36162eb8398ef24b852f30eee223edbbafc140982a57c262589',
    'repeat/X01_POS/run/caprice.log': '76788ddd8b23067f9f5dd3a8943d8f12fd29364c583bc28df5bb9b84f7c7b253',
    'repeat/X01_POS/run/printer.dat': '500038a37d1be23d7db4efed10674acb5c1d94094c9cf0bf11a22d563f3a9217',
    'repeat/X01_POS/run/screen.png': 'ef1fa58206fcfebec3c33d0c8262908cd4ba0a9537e1a357dd97576d1e1e1272',
    'repeat/X02_NEG/capture.json': 'fe17ec5bc7371027b43937f7c1fb95b1e169cb354c308f65161de4c85b344e27',
    'repeat/X02_NEG/list/caprice.log': '85a3e3830fa385e442d9a0eb990d4d4b346200445cc1ae96a7ff8988a06b7588',
    'repeat/X02_NEG/list/printer.dat': '2b2d428e8300886036a1d406ca7f2ec4be108bc4abeeec51e9a221cdf033fd08',
    'repeat/X02_NEG/list/screen.png': 'a08591b05274ad585d18cbe9a678c5e3a56b6c673320d185372e5696f70789ec',
    'repeat/X02_NEG/program.bin': 'f21bbb94f9f8c2eb3df1321b2f15f5a9863adcca61a94670cc4ad3b51ebfd6d3',
    'repeat/X02_NEG/run/caprice.log': '93eb017d9a7717a033e858b3fc0fc6ed65ad28a1e8c51a2da458183254000db7',
    'repeat/X02_NEG/run/printer.dat': '462d40b148cee1d5333282ab85e326ab458fbe604cd36a79cdbbb6a9daeae63c',
    'repeat/X02_NEG/run/screen.png': 'cd03b4b5561ccbce87456086b3c2a08c26c03e8b7e637aff32ed72ba364ac22a',
}
EXTERNAL_ORIGINAL_ZIP_SHA256 = '60977e10abae836f6c59adc3f54b51829abc8a5e65e802efb289fcd0f053df3b'

class Invalid(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise Invalid(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    require(path.is_file() and not path.is_symlink(), 'MISSING_OR_SYMLINK_' + str(path))
    return path.read_bytes()

def encoding(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')

def corpus():
    raw = read(DIR / 'corpus.json')
    require(digest(raw) == CORPUS_SHA256, 'CORPUS_PIN_MISMATCH')
    obj = json.loads(raw)
    require(obj.get('schema') == 1 and obj.get('phase') == PHASE and
            obj.get('base_sha') == BASE, 'CORPUS_SCHEMA')
    cases = obj.get('cases')
    require(isinstance(cases, dict) and 20 <= len(cases) <= 24, 'CORPUS_COUNT')
    require(all(re.fullmatch(r'[A-Z][A-Z0-9_]+', c) for c in cases), 'CASE_IDS')
    return cases

def check_sources():
    cases = corpus()
    paths = {p.name for p in (DIR / 'sources').glob('*')}
    require(paths == {c.lower() + '.bas' for c in cases}, 'SOURCES_INVENTORY')
    families = [v['family'] for v in cases.values()]
    for op in ('AND', 'OR', 'XOR', 'NOT'):
        require(families.count(op) >= 2, 'OPERATOR_COVERAGE_' + op)
    require(families.count('PRECEDENCE') >= 4 and
            families.count('PARENTHESES') >= 2 and
            families.count('RELATION_IF') >= 2 and
            families.count('DIAGNOSTIC') >= 2, 'MATRIX_COVERAGE')
    for c, entry in cases.items():
        data = read(DIR / 'sources' / (c.lower() + '.bas'))
        require(data == ('\n'.join(entry['lines']) + '\n').encode('ascii') and
                digest(data) == entry['source_sha256'] and
                entry['evidence_status'] == 'UNVERIFIED', 'SOURCE_CHANGED_' + c)
        require(entry['lines'][0].startswith('10 ') and
                entry['lines'][-1].startswith(('20 END', '30 END')), 'LINE_FORM_' + c)
        require(entry['expression'] in entry['lines'][0], 'EXPRESSION_DRIFT_' + c)
    return cases

def repo_head():
    return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                   text=True).strip()

def check_head(head):
    require(bool(re.fullmatch('[0-9a-f]{40}', head or '')), 'HEAD_FORMAT')
    require(repo_head() == head, 'HEAD_MISMATCH')
    require(subprocess.run(['git', '-C', str(ROOT), 'merge-base',
                            '--is-ancestor', BASE, head], capture_output=True).returncode == 0,
            'BASE_NOT_ANCESTOR')

def head_is_ancestor(head):
    return bool(re.fullmatch('[0-9a-f]{40}', head or '')) and subprocess.run(
        ['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', head, 'HEAD'],
        capture_output=True).returncode == 0

def oracle_modules():
    sys.path.insert(0, str(ROOT / 'tools'))
    sys.path.insert(0, str(ROOT / 'tests/oracles'))
    import j1_18_a_ink_evidence as ink
    import token_ram_oracle as cpc
    require(cpc.PIN == CAPRICE and cpc.ROM_SHA == ROM and ink.GHCR == GHCR,
            'EMULATOR_PIN_DRIFT')
    return ink, cpc

def commands(case, entry, stage):
    prefix = ['MODE 1', 'NEW'] + entry['lines']
    if stage == 'list':
        return prefix + ['LIST', 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT',
                         'LIST #8', 'CAP32_DELAY CAP32_EXIT']
    require(stage == 'run', 'BAD_STAGE')
    return prefix + ['RUN', 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                     'PRINT #8,"@@J122ERR@@";ERR;",";ERL', 'LIST #8',
                     'CAP32_DELAY CAP32_EXIT']

def parse_output(raw):
    require(raw.count(ERR_TAG) == 1, 'ERR_TAG_MISSING_OR_DUPLICATE')
    result, tail = raw.split(ERR_TAG)
    m = re.match(rb'\s*(\d+)\s*,\s*(\d+)\s*[\r\n]+', tail)
    require(m is not None, 'ERR_ERL_UNREADABLE')
    err, erl = int(m.group(1)), int(m.group(2))
    listed = tail[m.end():]
    require(bool(listed), 'POST_RUN_LIST_MISSING')
    return result, err, erl, listed

def token_bytes(program, cpc, entry):
    nums, rows = cpc.records(program)
    require(nums == [int(x.split(' ', 1)[0]) for x in entry['lines']], 'RAM_LINE_NUMBERS')
    first = rows[0]
    body = program[first['offset'] + 4:first['offset'] + first['length'] - 1]
    # Static ROM tokens are *structural checks*, not evidence of evaluation.
    token = {'AND': 0xfa, 'OR': 0xfc, 'XOR': 0xfd, 'NOT': 0xfe}
    operators = [op for op in token if re.search(r'\b' + op + r'\b', entry['lines'][0])]
    require(all(bytes([token[op]]) in body for op in operators), 'RAM_OPCODE_MISSING')
    return nums, rows, body.hex(' ').upper()

def acquire(cap, out, head):
    cases = check_sources()
    check_head(head)
    require(not out.exists(), 'DESTINATION_EXISTS')
    ink, cpc = oracle_modules()
    version = ink.check_caprice(cap)
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='j122-caprice-sna-') as td:
        for session in SESSIONS:
            for case, entry in cases.items():
                target = out / session / case
                snap = Path(td) / (session + '-' + case)
                snap.mkdir()
                lc, rc = commands(case, entry, 'list'), commands(case, entry, 'run')
                lm = ink.launch(cap, target / 'list', snap, lc, True)
                snapshots = list(snap.glob('*.sna'))
                require(len(snapshots) == 1, 'SNA_COUNT_' + case)
                program, region = cpc.extract_snapshot(
                    read(snapshots[0]), [int(x.split(' ', 1)[0]) for x in entry['lines']])
                nums, rows, body = token_bytes(program, cpc, entry)
                (target / 'program.bin').write_bytes(program)
                rm = ink.launch(cap, target / 'run', Path(td), rc, True)
                list_raw = read(target / 'list/printer.dat')
                result, err, erl, post_list = parse_output(read(target / 'run/printer.dat'))
                require(list_raw and list_raw == post_list, 'LIST_CHANGED_OR_MISSING_' + case)
                capture = {'phase': PHASE, 'case': case, 'session': session,
                           'source_sha256': entry['source_sha256'], 'ram_hex': program.hex(' ').upper(),
                           'region': region, 'numbers': nums, 'expression_record_hex': body,
                           'list_hex': list_raw.hex().upper(), 'result_hex': result.hex().upper(),
                           'err': err, 'erl': erl,
                           'commands': {'list': lc, 'run': rc},
                           'processes': {'list': lm, 'run': rm},
                           'screen_diagnostic': 'UNVERIFIED_PENDING_HUMAN_TRANSCRIPTION',
                           'semantics': 'CPC_OBSERVATION_NOT_HOST_PREDICTION'}
                (target / 'capture.json').write_bytes(encoding(capture))
                print(PHASE, session, case, 'RAM', digest(program),
                      'RESULT_HEX', capture['result_hex'], 'ERR', err, 'ERL', erl, flush=True)
    expected = {f'{s}/{c}/{p}' for s in SESSIONS for c in cases for p in FILESET}
    manifest = {'schema': 1, 'phase': PHASE, 'base_sha': BASE, 'acquisition_head': head,
                'run_id': os.environ.get('GITHUB_RUN_ID', 'LOCAL'),
                'oracle': {'rom_sha256': ROM, 'caprice_commit': CAPRICE,
                           'ghcr': GHCR, 'version': version, 'model': 'CPC6128', 'basic': '1.1'},
                'cases': list(cases), 'sessions': list(SESSIONS),
                'files': {p: digest(read(out / p)) for p in sorted(expected)},
                'external_seals': 'PENDING_EXTERNAL_ORIGINAL_ACTIONS_ARTIFACT',
                'snapshots_archived': False, 'native_changes': False}
    (out / 'manifest.json').write_bytes(encoding(manifest))
    verify(out, permanent=False)
    print(PHASE, 'FRESH_ACQUISITION_UNSEALED', len(cases)*2,
          'MANIFEST_SHA256', digest(read(out/'manifest.json')), flush=True)
    for p in sorted(expected):
        print('EXTERNAL_SHA256', p, digest(read(out/p)), flush=True)

def verify(out, permanent=True):
    cases = check_sources()
    raw_manifest = read(out / 'manifest.json')
    m = json.loads(raw_manifest)
    require(m.get('schema') == 1 and m.get('phase') == PHASE and
            m.get('base_sha') == BASE and m.get('cases') == list(cases) and
            m.get('sessions') == list(SESSIONS) and
            m.get('snapshots_archived') is False and m.get('native_changes') is False and
            m.get('external_seals') == 'PENDING_EXTERNAL_ORIGINAL_ACTIONS_ARTIFACT' and
            m.get('oracle',{}).get('rom_sha256') == ROM and
            m.get('oracle',{}).get('caprice_commit') == CAPRICE and
            m.get('oracle',{}).get('ghcr') == GHCR and
            m.get('oracle',{}).get('model') == 'CPC6128' and
            m.get('oracle',{}).get('basic') == '1.1', 'PROVENANCE_MISMATCH')
    require(head_is_ancestor(m.get('acquisition_head')), 'FAKE_HEAD')
    paths = {f'{s}/{c}/{f}' for s in SESSIONS for c in cases for f in FILESET}
    actual = {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()}
    require(actual == paths | {'manifest.json'} and set(m.get('files',{})) == paths,
            'ARCHIVE_INVENTORY')
    if permanent:
        require(bool(re.fullmatch(r'[a-f0-9]{64}', EXTERNAL_MANIFEST_SHA256 or '')) and
                m['acquisition_head'] == EXTERNAL_ACQUISITION_HEAD and
                digest(raw_manifest) == EXTERNAL_MANIFEST_SHA256 and
                set(EXTERNAL_FILE_SHA256) == paths, 'EXTERNAL_SEALS_MISSING_OR_INVALID')
    for p in sorted(paths):
        contents = read(out / p)
        require(len(contents) > 0 and digest(contents) == m['files'][p], 'FILE_HASH_' + p)
        if permanent:
            require(digest(contents) == EXTERNAL_FILE_SHA256[p], 'EXTERNAL_FILE_HASH_' + p)
    _, cpc = oracle_modules()
    results = {}
    for session in SESSIONS:
        for case, entry in cases.items():
            base = out / session / case
            cap = json.loads(read(base / 'capture.json'))
            program = read(base / 'program.bin')
            nums, rows, body = token_bytes(program, cpc, entry)
            before = read(base / 'list/printer.dat')
            result, err, erl, after = parse_output(read(base / 'run/printer.dat'))
            require(before == after and before == bytes.fromhex(cap['list_hex']) and
                    result == bytes.fromhex(cap['result_hex']) and
                    cap['err'] == err and cap['erl'] == erl and
                    cap['ram_hex'] == program.hex(' ').upper() and
                    cap['numbers'] == nums and cap['expression_record_hex'] == body and
                    cap['source_sha256'] == entry['source_sha256'] and
                    cap['phase'] == PHASE and cap['case'] == case and
                    cap['session'] == session and
                    cap['commands'] == {t:commands(case,entry,t) for t in ('list','run')},
                    'CAPTURE_MISMATCH_' + case + session)
            for stage in ('list', 'run'):
                process = cap['processes'][stage]
                require(process['commands'] == commands(case,entry,stage) and
                        process['started_utc'] != process['finished_utc'] and
                        read(base / stage / 'caprice.log').startswith(b'exit code: 0\n'),
                        'PROCESS_NOT_PROVEN_' + case + session + stage)
                png = read(base / stage / 'screen.png')
                require(png[:8] == b'\x89PNG\r\n\x1a\n' and png[12:16] == b'IHDR' and
                        process['screenshot_width'] == int.from_bytes(png[16:20], 'big') and
                        process['screenshot_height'] == int.from_bytes(png[20:24], 'big'),
                        'SCREEN_INVALID_' + case + session + stage)
            results[case,session] = (program, before, result, err, erl,
                                     cap['processes']['list']['started_utc'],
                                     cap['processes']['run']['started_utc'])
    for case in cases:
        a,b = results[case,'original'], results[case,'repeat']
        require(a[:5] == b[:5] and a[5] != b[5] and a[6] != b[6],
                'INDEPENDENT_REPEAT_NOT_PROVEN_' + case)
    return {'cases': len(cases), 'sessions': len(cases)*2,
            'status': 'EXTERNALLY_SEALED' if permanent else 'UNSEALED_NOT_AN_ORACLE'}

def falsifications(out):
    """Run only against a verified externally sealed archive; never edit it."""
    verify(out, permanent=True)
    case = next(iter(corpus()))
    mutations = ('ram', 'printer', 'list', 'capture', 'png', 'log',
                 'missing_file', 'rom', 'head', 'repeat', 'coordinated_rehash')
    for kind in mutations:
        with tempfile.TemporaryDirectory(prefix='j122-negative-') as tmp:
            copy = Path(tmp) / 'archive'
            shutil.copytree(out, copy)
            victim = copy/'original'/case
            file = {'ram':'program.bin', 'printer':'run/printer.dat',
                    'list':'list/printer.dat', 'capture':'capture.json',
                    'png':'run/screen.png', 'log':'run/caprice.log',
                    'missing_file':'program.bin', 'repeat':'program.bin',
                    'coordinated_rehash':'program.bin'}.get(kind)
            if kind in ('rom','head'):
                m = json.loads(read(copy/'manifest.json'))
                if kind == 'rom': m['oracle']['rom_sha256'] = '0'*64
                else: m['acquisition_head'] = '0'*40
                (copy/'manifest.json').write_bytes(encoding(m))
            elif kind == 'repeat':
                data = read(copy/'repeat'/case/file)
                (victim/file).write_bytes(data + b'X')
            elif kind == 'missing_file': (victim/file).unlink()
            else:
                original = read(victim/file)
                (victim/file).write_bytes(original + b'X')
                if kind == 'coordinated_rehash':
                    m = json.loads(read(copy/'manifest.json'))
                    key = 'original/'+case+'/'+file
                    m['files'][key] = digest(read(victim/file))
                    (copy/'manifest.json').write_bytes(encoding(m))
            try: verify(copy, permanent=True)
            except (Invalid, ValueError, KeyError, IndexError, UnicodeError):
                print(PHASE, 'FALSIFICATION_REJECTED', kind, flush=True)
            else: raise Invalid('FALSIFICATION_ACCEPTED_' + kind)
    return len(mutations)

def self_test():
    check_sources()
    with tempfile.TemporaryDirectory(prefix='j122-empty-') as td:
        for path in (Path(td), Path(td)/'missing'):
            try: verify(path, permanent=True)
            except Invalid: pass
            else: raise Invalid('EMPTY_ARCHIVE_FALSE_PASS')
        partial = Path(td)/'partial'
        partial.mkdir()
        (partial/'manifest.json').write_bytes(b'{}\n')
        try: verify(partial, permanent=True)
        except Invalid: pass
        else: raise Invalid('PARTIAL_ARCHIVE_FALSE_PASS')
    require(EXTERNAL_MANIFEST_SHA256 is None or bool(re.fullmatch(
            r'[a-f0-9]{64}', EXTERNAL_MANIFEST_SHA256)), 'PARTIAL_SEAL')
    print(PHASE, 'OFFLINE_CONTRACT_PASS', len(corpus()), 'CASES',
          'NEGATIVE_SYNTHETIC', 3, 'CPC_OBSERVATIONS', 0, flush=True)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check-sources', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--acquire', type=Path)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--head')
    ap.add_argument('--verify', nargs='?', const=str(DIR), type=Path)
    ap.add_argument('--verify-unsealed', type=Path,
                    help='diagnostic only; NEVER an oracle PASS')
    args = ap.parse_args()
    require(any((args.check_sources,args.self_test,args.acquire,args.verify,
                 args.verify_unsealed)), 'OPERATION_REQUIRED')
    if args.check_sources: check_sources(); print(PHASE, 'SOURCES_PASS')
    if args.acquire:
        require(args.output is not None and args.verify is None, 'ACQUIRE_ARGS')
        acquire(args.acquire.resolve(),args.output.resolve(),args.head or repo_head())
    if args.verify_unsealed:
        print(PHASE, 'UNSEALED', verify(args.verify_unsealed.resolve(), False))
    if args.verify:
        print(PHASE, 'SEALED', verify(args.verify.resolve(), True))
        if args.self_test:
            print(PHASE, 'REAL_NEGATIVES_REJECTED', falsifications(args.verify.resolve()))
    elif args.self_test: self_test()

if __name__ == '__main__':
    try: main()
    except (Invalid, OSError, subprocess.SubprocessError, ValueError, KeyError,
            IndexError, UnicodeError, ImportError) as e:
        print(PHASE, 'FAIL', str(e), file=sys.stderr)
        sys.exit(1)
