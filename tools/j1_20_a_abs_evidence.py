#!/usr/bin/env python3
"""J1.20-A: genuinely run CPC6128/BASIC 1.1 ABS integer oracle.

No native ABS implementation. First acquisition is UNSEALED; external SHA
pins are separately added only after archive commit and independent CI logs.
"""
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
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/oracles'))
sys.path.insert(0,str(ROOT/'tools'))
import token_ram_oracle as cpc
import j1_18_a_ink_evidence as ink

CASES={
 'A00': '10 PRINT ABS(0)\n20 PRINT #8,ABS(0)\n30 END\n',
 'A01': '10 PRINT ABS(1)\n20 PRINT #8,ABS(1)\n30 END\n',
 'AN1': '10 PRINT ABS(-1)\n20 PRINT #8,ABS(-1)\n30 END\n',
 'V07': '10 A%=7\n20 PRINT ABS(A%)\n30 PRINT #8,ABS(A%)\n40 END\n',
 'VN7': '10 A%=-7\n20 PRINT ABS(A%)\n30 PRINT #8,ABS(A%)\n40 END\n',
 'VMAX': '10 A%=32767\n20 PRINT ABS(A%)\n30 PRINT #8,ABS(A%)\n40 END\n',
 'VNMAX': '10 A%=-32767\n20 PRINT ABS(A%)\n30 PRINT #8,ABS(A%)\n40 END\n',
 'VMIN': '10 A%=-32768\n20 PRINT ABS(A%)\n30 PRINT #8,ABS(A%)\n40 END\n',
 'B07': '10 A%=7\n20 B%=ABS(A%)\n30 PRINT B%\n40 PRINT #8,B%\n50 END\n',
 'BN7': '10 A%=-7\n20 B%=ABS(A%)\n30 PRINT B%\n40 PRINT #8,B%\n50 END\n',
 'BMIN': '10 A%=-32768\n20 B%=ABS(A%)\n30 PRINT B%\n40 PRINT #8,B%\n50 END\n',
 'IMIN': '10 PRINT ABS(-32768)\n20 PRINT #8,ABS(-32768)\n30 END\n',
 'L20': '10 REM CHECK LINE 20\n20 PRINT ABS(-32768)\n30 PRINT #8,ABS(-32768)\n40 END\n',
 'EMPTY': '10 PRINT ABS()\n20 PRINT #8,88\n30 END\n',
 'STRING': '10 PRINT ABS("X")\n20 PRINT #8,88\n30 END\n',
 'MULTI': '10 PRINT ABS(1,2)\n20 PRINT #8,88\n30 END\n',
}
SESSIONS=('original','repeat')
PHASE='J1.20-A'
DEST=ROOT/'tests/fixtures/cpc6128/j1_20_a_abs'
SOURCES=ROOT/'tests/oracles/inputs/j1_20_a'
GHCR=ink.GHCR
# To be inserted FROM FIRST REAL CI ACQUISITION LOGS after archived Git commit.
SEALED_MANIFEST='28dd0ec2a15aa52bdf4b0e5b79762d572e3fb39f204002eaf194246177111ac3'
SEALED={
  "original/A00/capture.json": "3defc6ea8718e814c5e283a5348c4e4786194ac0badc79d8d142ed2f4980ccb6",
  "original/A00/list/caprice.log": "b1c94da7caaf3c602eec4aa164062aacf85b1f62ff422c5d5840445749a05983",
  "original/A00/list/screen.png": "4b32ae64f19d8689f23d8e66dcd76b4177a2d22a4684012073b863601535092f",
  "original/A00/program.bin": "741e735e23b2274faa29265bf846ef6cba5cd335384f05897307a89457555efd",
  "original/A00/run/caprice.log": "c350d1dfb394940097a354c1e5156f64515d875ecf0f625ec5f3c0cd93195807",
  "original/A00/run/printer.dat": "14d4074ee78cd7806ef6dabf9a3f876207fd8891513675535c9751e55678e649",
  "original/A00/run/screen.png": "2a2283f46a9bc862ca1d568c63f45d72111839d4c6ee1a7f73093f206aeed214",
  "original/A01/capture.json": "cf2ba55d3c5fc39297f7cda79192dc1713fce2174487a34ea6b0602ab14234f1",
  "original/A01/list/caprice.log": "05d7c815163d5d9e02a62c7e409aed46118c587c77eb2c4257eabe242ef6a685",
  "original/A01/list/screen.png": "cab31105f968b39cf63c44fa8b60025aa507a399442c05fbee90fe6e9f9c67f4",
  "original/A01/program.bin": "a0c94ae77f96d59a40e21ddf60616a9d3899b4c2c4a4313c9295252978a19421",
  "original/A01/run/caprice.log": "5b0da93d92c4c8d22b8102d2bdb784bc92f2729e8059c123a7514e0f36ab8aac",
  "original/A01/run/printer.dat": "c0b76a05e94eb5216609ce7e5711463428f65ef181f30a6f5d4e0e9a95433ecb",
  "original/A01/run/screen.png": "09a5a4cf516d9cd7b14734b461ef17943e6c6203fe9b31aebf0161279417236f",
  "original/AN1/capture.json": "08c6aaaefb78d206ec828c821c2a59dc1a176541e4b7bf038df14914c4b3601a",
  "original/AN1/list/caprice.log": "4e0f9b6edb488fcf5a73a6777db6b54a14b9d965acdf355df01624b732c3a1d5",
  "original/AN1/list/screen.png": "0f0e1dbe31e576e7316eab6bbb8370af6d9c335cdb9646911491d500ddb6ef04",
  "original/AN1/program.bin": "b1f5f4fe6920b8990e2a1d2d4f955f013c35e87a08bf5f95d2703e0b2478d708",
  "original/AN1/run/caprice.log": "2cff9d8974e6616e4cca64c3b4f81a4c36e03a33146637f8116c8faa7495d1a2",
  "original/AN1/run/printer.dat": "c0b76a05e94eb5216609ce7e5711463428f65ef181f30a6f5d4e0e9a95433ecb",
  "original/AN1/run/screen.png": "912bd1049d9295bc0683aa7cd1576a9ecd7fadb58203f00845ce783de3324bb7",
  "original/B07/capture.json": "665f5d71d3b47b96bb4b684d0b40dd7e4deff3c25dbcaee2bfe6deb09d370718",
  "original/B07/list/caprice.log": "ef0417fa4f88c2401b3f82a44e5f56a0081774d89a679d132393b611df510797",
  "original/B07/list/screen.png": "d33a5b2abdf0530fb8c3f66e1225e4c7b29d6fd523c4f9a2deee098f710efea7",
  "original/B07/program.bin": "613597a7bbea54a936f9c9e3e851ec993241076b4aff53c4bad2e305468aff98",
  "original/B07/run/caprice.log": "6124bed354092961eaae6b94e6d04fc4759a370dfc622eaffc7bebeafcc999b0",
  "original/B07/run/printer.dat": "9bd23b1b61e0d23061ee673bda828b2262cb56d41badb948b75e1f602175c869",
  "original/B07/run/screen.png": "28c0bce565ed80acf447bf9b3d466fb068222c0bac5e9c951ec4774c1f9889bc",
  "original/BMIN/capture.json": "ad98095ad6b0d0e13c4236d92f9bcf2ed24ddf7fb535a7e1045c857bb3c29d6d",
  "original/BMIN/list/caprice.log": "0dd6ad14e31d71ee39dfca07088e8038ef06f5d1feddeb87204f3811c3edae22",
  "original/BMIN/list/screen.png": "b1fba8e8ec8f9869dfcbdf0c4f9823f29750da512dd640c2d44504a871b2b9ed",
  "original/BMIN/program.bin": "3ca58f794189450e398b4a1e1ade0680bfd78bd4f84ddfca00f3d4160e12e7d1",
  "original/BMIN/run/caprice.log": "e08993058f787566e864c78669f1078ebf625f396d0cca372c538e206a54cc58",
  "original/BMIN/run/printer.dat": "2618c7980133a7565f4feca27a730d30255c9e4f03d1a72746409ae35026ad94",
  "original/BMIN/run/screen.png": "cac7d62825b0b7425ab65f4154f67162069fdf8958b6edfda20df2b02902e251",
  "original/BN7/capture.json": "d1e9c11b9d1121a97578843e915c62f8558729ab16bce90c516453f60d79ff74",
  "original/BN7/list/caprice.log": "e6c08f4da98cdb37f62df28522bd872b3ae03dbbb3578fabd58c50146013b8e9",
  "original/BN7/list/screen.png": "75d51260ba3b7123f7b4f6f702f3f8b5c7705bf2ab4bda216d9306e5599bcbd7",
  "original/BN7/program.bin": "8adf609ce9ab1ef5838831c72888116a73a1ffc30922d9fc9a36874dded41ace",
  "original/BN7/run/caprice.log": "5d097c249fda02137daadc51bd1d5de024a0992d49adbaad9463bd93ca6ea37d",
  "original/BN7/run/printer.dat": "9bd23b1b61e0d23061ee673bda828b2262cb56d41badb948b75e1f602175c869",
  "original/BN7/run/screen.png": "5602aae7790eed25b8a622483ab0f9b348da4bd309c412421bfbd0d212f72dfb",
  "original/EMPTY/capture.json": "3cd02735f61318eac0f9c1e24c85f93896b32d9772a0f733bbe2d923df94a28e",
  "original/EMPTY/list/caprice.log": "dee0f81ab12b6b978e47336128431aa71d8c36d7ccf7ea693464e5eeab8ec3d3",
  "original/EMPTY/list/screen.png": "37f6e3c0f54bfb729593f206aba7ff6badca1995a18e5d29e526101c8ed96154",
  "original/EMPTY/program.bin": "0745a13e0e8c0cc02fbff48edb9c433fb6161f873dfbb378dade14ef9376bfb5",
  "original/EMPTY/run/caprice.log": "97ece294903d5eed45ecf2ce0246f4f713c6940199c6f13956e97ba22bb3a573",
  "original/EMPTY/run/printer.dat": "2338e66dea8ccb7549764b33a93567db652406551928b79af207c44a82d09d40",
  "original/EMPTY/run/screen.png": "8e4f7ce1207b2af28113975f6231c22050f52630fe662cb18475826d53a85ad0",
  "original/IMIN/capture.json": "d9d72bf29e2bbee761d18dc87d9d7d1060d31449296686b247f25d9e145e1fe7",
  "original/IMIN/list/caprice.log": "20651fa4ef5ddbab8f5d4c7ad1607dbb576866cb87d34db147e2514634fe4447",
  "original/IMIN/list/screen.png": "c4b3e715773a0a587dc41dc7daa7ac907ad6cb5db65ab801af36ae4822deb7df",
  "original/IMIN/program.bin": "aa24c54caf621247e0cea69062ff9050b957c111d2c96d10fdd7ca069c6e0b6b",
  "original/IMIN/run/caprice.log": "01af4deab83a6238002ed7afa5dfa04ac5e7a1b33cb497f1f5f43b76e651543c",
  "original/IMIN/run/printer.dat": "84356f9b36de2d1746360fdd9b89d2b76f49a996d503124eba14bfa71979ca50",
  "original/IMIN/run/screen.png": "1093dc9251fee9cd8b3e4ae400ab2a5af8a0d078ccdfb461d4723e0300098659",
  "original/L20/capture.json": "69097a83e6f818245283bc305324def94d27dfff17cc90268d610a1f534fe50b",
  "original/L20/list/caprice.log": "11f36aa72a6eae3cbb6d21d6487ef8cbcf2bcabd2a90a8d5472653f9f3e93708",
  "original/L20/list/screen.png": "04a9bb74f67d880ea73d552b63deb89f91002e10717cec22bd1380aacdea417d",
  "original/L20/program.bin": "69e6a6791c7200322a59d41f1e6a56ddbb1fc92e2f56798b599ab4cc5602fb62",
  "original/L20/run/caprice.log": "8ed445ecab5ecf488bc0617c424403bb7cd01ea1dc269633f3c8cb69fd16a668",
  "original/L20/run/printer.dat": "dc23927e99e4cdd73e57e30c6d5742ba46b00d7cf3f71ea373b30d9269a8a9cb",
  "original/L20/run/screen.png": "bbb81c26865a8104044c0c471fa0606d9eb13934cf1583393485251868b1b8a1",
  "original/MULTI/capture.json": "3415d9fbb5f43bf06596f224bc44521a89ec9242272cb525744e67efdd3dde48",
  "original/MULTI/list/caprice.log": "4ba017365abc51f10c51b559db85281ee06464969bc5e7bbdb7159194a9fb90e",
  "original/MULTI/list/screen.png": "9b9b04d97c8fcbcbfc4b6416f0d69abaedade8379b5824910b90b602167d125c",
  "original/MULTI/program.bin": "2657d019960a78721551313af93d15f236f3e2be248c0e70d6bd596ba7e12335",
  "original/MULTI/run/caprice.log": "14dcba371ec0783bd853a59432aee3e3c26daa956bfea89a1fe020e0a5ebc9bb",
  "original/MULTI/run/printer.dat": "2338e66dea8ccb7549764b33a93567db652406551928b79af207c44a82d09d40",
  "original/MULTI/run/screen.png": "d563249822a762fab511bd5482ac32a6fb94c4ce82a35af9d77e63d9b4db8ffa",
  "original/STRING/capture.json": "d7c409c1a2c0fe2a9fe63d576245e1614106da26ce1d3b205126215e1114996f",
  "original/STRING/list/caprice.log": "27ea8e67d7e9fac6c3b52a08392f03fda0fe50bfd92b051068a7bec811398516",
  "original/STRING/list/screen.png": "5ab3631f79049d27cb81540d5b473d70b3f91b90ea82766416cdd76a8fcf47f8",
  "original/STRING/program.bin": "b6d988aea29e6b3b848ae3378550350d88585a7cc5762cc2fb51afd054793b10",
  "original/STRING/run/caprice.log": "c507f062d4e4d9c64132dbae933beaf560b1522d998af244b6b5d2bf1085dd7d",
  "original/STRING/run/printer.dat": "179686fc37902ac7ec8d3cbf3997cbd4d032fc28780c44ad31482e4b13e15e23",
  "original/STRING/run/screen.png": "b1377343e6a825eb5eef032c2847067400478480f0fbd67219d008e8bdf51bce",
  "original/V07/capture.json": "6d07c2f0a4fefdedc61ad5e720c90a382912b555281c63bda7c803a41f3b32a2",
  "original/V07/list/caprice.log": "58f23c368e58945ef906e2f7db494feb91f8ce682bebc89dccd1c5b27e20c3e4",
  "original/V07/list/screen.png": "25b5ec6d3396bf53c6cf0e766f4dda008e6f39bdd46b14d0c40b9d05ea2b3a1f",
  "original/V07/program.bin": "d56c9c6fe16f8766e3e565a09f6aa4a81447e306c45afd78dc21884df5887812",
  "original/V07/run/caprice.log": "8d87c2acf97bb2c96f89945392249aba2e23c76f830f303adaba2f6db12c7f0d",
  "original/V07/run/printer.dat": "9bd23b1b61e0d23061ee673bda828b2262cb56d41badb948b75e1f602175c869",
  "original/V07/run/screen.png": "cf63a2e7d147b77d598c1a577adcbb43aeb4ee716926d0f086a8953e3b07b037",
  "original/VMAX/capture.json": "96d80d51aa9ea20de3e0e35699b30d90686287ff60a08682d2545254442423aa",
  "original/VMAX/list/caprice.log": "dd2bb9b104d9ff8e9190595f9f58badf10cf03dae90c485c9f858700ff0a4693",
  "original/VMAX/list/screen.png": "26fd25337a84c30f3af787df7eec8693b7f559bf7b2e1666a9dd874571e7044e",
  "original/VMAX/program.bin": "2479172217b01d771aad88bef1bcf9d053d2af40987594923771c50064324f6f",
  "original/VMAX/run/caprice.log": "5f5baee909df2439985ea274a1c857c42439862f195b839aaaf4ee663b889bf5",
  "original/VMAX/run/printer.dat": "32ddfd7d493a41b8b85e364a9e1bbeacffd97e9527ca70248a3bf7a36d684a86",
  "original/VMAX/run/screen.png": "cf8ac6a4747f9808875f4a9436e5bd1847ce2710cf5c9599f4ba6698b14815ad",
  "original/VMIN/capture.json": "a7ff1066fb368fc598df492aef39a2ac5da185e8d81f51db3c3d82ee6fd175b3",
  "original/VMIN/list/caprice.log": "01487f103817eb96cff0dc32783d71c15827d82d5b04a6d89774cd9b599a38d1",
  "original/VMIN/list/screen.png": "95b7c1f3c79d3f7bc249b182eed46d663c85ff05ec51c650d57742ac248cc551",
  "original/VMIN/program.bin": "4bdbbf5976a245ad8b7de081a146353c1f05124ccbde2ee9bb8b323223ca86ac",
  "original/VMIN/run/caprice.log": "5b88cd96fc1e71ec34990ad9c10e871ce104a3132259b82d3d018ffcfbbac9d9",
  "original/VMIN/run/printer.dat": "84356f9b36de2d1746360fdd9b89d2b76f49a996d503124eba14bfa71979ca50",
  "original/VMIN/run/screen.png": "88333b79f355fce87418da78f8cad4f5fcefe035785242a701bdc168df639321",
  "original/VN7/capture.json": "389dad229c0afff9c9408cebc949dc0ec7eec9bb835b89d20f6511835ca81b66",
  "original/VN7/list/caprice.log": "38fb86d7be56f964d6beaa44acefeabe2771aafb6884b4c425832e10e2a25187",
  "original/VN7/list/screen.png": "50357dfbcfb5569be3a3b932b12890e52e9a27b92ea7eb0ec470ec9b865e2649",
  "original/VN7/program.bin": "5d3a15a7b0b79ee60232134caa7152125e038812437820d8872a116b129f9caf",
  "original/VN7/run/caprice.log": "558e6ef9e3ae6731e6630027d2da179649aac3c521798a384e1daaeb276d5f74",
  "original/VN7/run/printer.dat": "9bd23b1b61e0d23061ee673bda828b2262cb56d41badb948b75e1f602175c869",
  "original/VN7/run/screen.png": "11fdcc1dd203f98ab3e41253ffe67f8d5f40aebb919e249741708518e22a53e8",
  "original/VNMAX/capture.json": "c0018b08bad7b6c9591a089e028f6dc7d136ffee20e08d5d486d78bfd1ce719c",
  "original/VNMAX/list/caprice.log": "ecb9c8ee67503ed399cbfe0256a4d68a95c8bdc467e0b7b39664a9df65f386d4",
  "original/VNMAX/list/screen.png": "f79b255e3a47705ed6906ea57d62d9d9e6c1cc43f96652c6684521ff57859543",
  "original/VNMAX/program.bin": "ebb7e192d639a604d7b255d17cf161b55caa4c3f0e5bed3a05eaeaa228beb34c",
  "original/VNMAX/run/caprice.log": "dd470964bb7d24f85fa0d078677eaed04639cf90a8d58dc3327ab1ef38b35a2b",
  "original/VNMAX/run/printer.dat": "32ddfd7d493a41b8b85e364a9e1bbeacffd97e9527ca70248a3bf7a36d684a86",
  "original/VNMAX/run/screen.png": "5b01ac03e33faa5115c965ee80d00b2387dd946764f3a13488100e404c7d6bd5",
  "repeat/A00/capture.json": "b3ccf89526101f48f15029ef3e1f1b432ecf56fe6651b9712306f5f7e3ee8649",
  "repeat/A00/list/caprice.log": "dde81f807a8dddc6d567075968ed98fa8636a8bcd0935f15d934a53f8c50721b",
  "repeat/A00/list/screen.png": "4b32ae64f19d8689f23d8e66dcd76b4177a2d22a4684012073b863601535092f",
  "repeat/A00/program.bin": "741e735e23b2274faa29265bf846ef6cba5cd335384f05897307a89457555efd",
  "repeat/A00/run/caprice.log": "f3150d72265f48746e0af5ad8de5c320ff642eecf2ea7eef09031fe6e0d72062",
  "repeat/A00/run/printer.dat": "14d4074ee78cd7806ef6dabf9a3f876207fd8891513675535c9751e55678e649",
  "repeat/A00/run/screen.png": "74e1179bc3995d49be2e530ae9fabdaa69ce7ad2d7fb6211c7f17d6f07578bb2",
  "repeat/A01/capture.json": "a2f625d54df333835cefc7d12487785a6295bf1c90597185fcd1518c4ec89408",
  "repeat/A01/list/caprice.log": "48e1bb4463a025ace686020ce4aa24bcb29ad325902e562d227feb49265bf93b",
  "repeat/A01/list/screen.png": "cab31105f968b39cf63c44fa8b60025aa507a399442c05fbee90fe6e9f9c67f4",
  "repeat/A01/program.bin": "a0c94ae77f96d59a40e21ddf60616a9d3899b4c2c4a4313c9295252978a19421",
  "repeat/A01/run/caprice.log": "6bca616f7fec406098b3aa6acaa5e3a539562480165f4070be0d7d62daff5954",
  "repeat/A01/run/printer.dat": "c0b76a05e94eb5216609ce7e5711463428f65ef181f30a6f5d4e0e9a95433ecb",
  "repeat/A01/run/screen.png": "09a5a4cf516d9cd7b14734b461ef17943e6c6203fe9b31aebf0161279417236f",
  "repeat/AN1/capture.json": "f71ba4895f7b386c27bb0b8198a2db51fd66dc02b70985ece80a5dc81d98d9fa",
  "repeat/AN1/list/caprice.log": "4ac15ebcd198f6c5905f8a5f356ce92274e42889ef7f7407586c9a1a2ce2f179",
  "repeat/AN1/list/screen.png": "0f0e1dbe31e576e7316eab6bbb8370af6d9c335cdb9646911491d500ddb6ef04",
  "repeat/AN1/program.bin": "b1f5f4fe6920b8990e2a1d2d4f955f013c35e87a08bf5f95d2703e0b2478d708",
  "repeat/AN1/run/caprice.log": "a0703559eb0a22d59cfc46c6cd36ba00ccb3811cafb959e83b9518e1307289c5",
  "repeat/AN1/run/printer.dat": "c0b76a05e94eb5216609ce7e5711463428f65ef181f30a6f5d4e0e9a95433ecb",
  "repeat/AN1/run/screen.png": "912bd1049d9295bc0683aa7cd1576a9ecd7fadb58203f00845ce783de3324bb7",
  "repeat/B07/capture.json": "9e6a168ee2460d536ea3255a49d2151c91b7e6dcf42ab8c985aa8d486416d733",
  "repeat/B07/list/caprice.log": "d3f48a6ed50cdb2bd30d6047e4ee73d9b8f3a7b11319fc0a473f706d75a7850d",
  "repeat/B07/list/screen.png": "afb19ece9867cda01e09edeed315865a484898557bab0e569b59fd6e656376f7",
  "repeat/B07/program.bin": "613597a7bbea54a936f9c9e3e851ec993241076b4aff53c4bad2e305468aff98",
  "repeat/B07/run/caprice.log": "7ce89d30a6abd0dde2f2280d2c1c45a648319cb9cd77942e3e60e07394d51c6a",
  "repeat/B07/run/printer.dat": "9bd23b1b61e0d23061ee673bda828b2262cb56d41badb948b75e1f602175c869",
  "repeat/B07/run/screen.png": "28c0bce565ed80acf447bf9b3d466fb068222c0bac5e9c951ec4774c1f9889bc",
  "repeat/BMIN/capture.json": "1be0162a36c5fa797fa902eef682b84b693cf8ac200216e8e9d0f873ae624f6f",
  "repeat/BMIN/list/caprice.log": "37d1f2806c3d54cc2640468a985baf1e35d2c749d7dc53295fe47a7d0ea8056d",
  "repeat/BMIN/list/screen.png": "435ee48e52ce3c943cdfaf532da2f9d00d882b83a44d0bac177809f9f1cea45b",
  "repeat/BMIN/program.bin": "3ca58f794189450e398b4a1e1ade0680bfd78bd4f84ddfca00f3d4160e12e7d1",
  "repeat/BMIN/run/caprice.log": "cab5ad3833c0d12f1ababf9f18d90739acb9e567009e6151713b4e3413ede9ab",
  "repeat/BMIN/run/printer.dat": "2618c7980133a7565f4feca27a730d30255c9e4f03d1a72746409ae35026ad94",
  "repeat/BMIN/run/screen.png": "866ec83fb242754bf06ea9c42f49695ef9cc6dfb0e125fcd0fa51f815293c9f1",
  "repeat/BN7/capture.json": "47fb4e3d80ba147d20a4be30046616e5a912b081feeca1849a5d6912854fd5ea",
  "repeat/BN7/list/caprice.log": "a95f180525582b45db938dd187d3d7efee225faef5db61386b9901cd5399a361",
  "repeat/BN7/list/screen.png": "75d51260ba3b7123f7b4f6f702f3f8b5c7705bf2ab4bda216d9306e5599bcbd7",
  "repeat/BN7/program.bin": "8adf609ce9ab1ef5838831c72888116a73a1ffc30922d9fc9a36874dded41ace",
  "repeat/BN7/run/caprice.log": "9a4ec2e51e1e91517263567e22b2c3ab658c2fad122fd22c9ed6d5d20102f92e",
  "repeat/BN7/run/printer.dat": "9bd23b1b61e0d23061ee673bda828b2262cb56d41badb948b75e1f602175c869",
  "repeat/BN7/run/screen.png": "a242b2531d551321bd5b2ead9b4b2b7cf60f51226c1c64df6f3daa2f894e7867",
  "repeat/EMPTY/capture.json": "a2c2fece95d8117a28f898b942afdf18ffb83077ee49899121ac4ac3d50617e1",
  "repeat/EMPTY/list/caprice.log": "60e51f066d8bdba31c2fc9f601ba8d70f892ebe5ce4d567e0b54d670225dd052",
  "repeat/EMPTY/list/screen.png": "37f6e3c0f54bfb729593f206aba7ff6badca1995a18e5d29e526101c8ed96154",
  "repeat/EMPTY/program.bin": "0745a13e0e8c0cc02fbff48edb9c433fb6161f873dfbb378dade14ef9376bfb5",
  "repeat/EMPTY/run/caprice.log": "e229b11174856442150f174b245e630f43f9bdb1113d583e8d8d112b987aa5fc",
  "repeat/EMPTY/run/printer.dat": "2338e66dea8ccb7549764b33a93567db652406551928b79af207c44a82d09d40",
  "repeat/EMPTY/run/screen.png": "8e4f7ce1207b2af28113975f6231c22050f52630fe662cb18475826d53a85ad0",
  "repeat/IMIN/capture.json": "9ac2d30eb3549e353e58405c4945689fbc58795ceea6f61b89db8665085f5fa5",
  "repeat/IMIN/list/caprice.log": "6ab669e2927cd38d747e106c3efc90bf841906e79af43cf91e66756badc8068e",
  "repeat/IMIN/list/screen.png": "c4b3e715773a0a587dc41dc7daa7ac907ad6cb5db65ab801af36ae4822deb7df",
  "repeat/IMIN/program.bin": "aa24c54caf621247e0cea69062ff9050b957c111d2c96d10fdd7ca069c6e0b6b",
  "repeat/IMIN/run/caprice.log": "8c3dcd791907f3f7fd578f405704c71f0ed0518f98f5a4f059e9406f28e023c1",
  "repeat/IMIN/run/printer.dat": "84356f9b36de2d1746360fdd9b89d2b76f49a996d503124eba14bfa71979ca50",
  "repeat/IMIN/run/screen.png": "1093dc9251fee9cd8b3e4ae400ab2a5af8a0d078ccdfb461d4723e0300098659",
  "repeat/L20/capture.json": "2c912f56d6748e5583b0a9bda23331ad5d1b8b31b42d2638aaefc462e9dc6103",
  "repeat/L20/list/caprice.log": "74bb7de1b7f55c85e68ca76e745e6cbd54d5a25041c65ec4fa87aa57117a2626",
  "repeat/L20/list/screen.png": "b128e188f821adb0084c7e50736d06711a743047c7362be6f97f024642914f3c",
  "repeat/L20/program.bin": "69e6a6791c7200322a59d41f1e6a56ddbb1fc92e2f56798b599ab4cc5602fb62",
  "repeat/L20/run/caprice.log": "aa5feec43cb02ea55d28331b447de0975854d10d4e13c3c88d7d1b9a4b5a2896",
  "repeat/L20/run/printer.dat": "dc23927e99e4cdd73e57e30c6d5742ba46b00d7cf3f71ea373b30d9269a8a9cb",
  "repeat/L20/run/screen.png": "f03ac239b3f7f1af9079e3183611f845b9b1db032d556fa8026023b11e1c18ae",
  "repeat/MULTI/capture.json": "2f423a300432a7afa64087a3130466feec210b9c52322a4638d6509d9ec0b71c",
  "repeat/MULTI/list/caprice.log": "f07b322dc267a57e1d067efe751153d6cc321149de694c9c7b950e83b859bd59",
  "repeat/MULTI/list/screen.png": "9b9b04d97c8fcbcbfc4b6416f0d69abaedade8379b5824910b90b602167d125c",
  "repeat/MULTI/program.bin": "2657d019960a78721551313af93d15f236f3e2be248c0e70d6bd596ba7e12335",
  "repeat/MULTI/run/caprice.log": "7f360f2039955ba7c012b463ca8029a9189f1489f1fa9faa6d84df002455877d",
  "repeat/MULTI/run/printer.dat": "2338e66dea8ccb7549764b33a93567db652406551928b79af207c44a82d09d40",
  "repeat/MULTI/run/screen.png": "d563249822a762fab511bd5482ac32a6fb94c4ce82a35af9d77e63d9b4db8ffa",
  "repeat/STRING/capture.json": "1e5cb95acd013745b5c4ca48710716c5d3a5f8f9c0038b084989eebd1faf44d6",
  "repeat/STRING/list/caprice.log": "dad4b98760018ea4787edcba7301f1d36e45b3f2fed101acfa997b0d415a72c7",
  "repeat/STRING/list/screen.png": "5ab3631f79049d27cb81540d5b473d70b3f91b90ea82766416cdd76a8fcf47f8",
  "repeat/STRING/program.bin": "b6d988aea29e6b3b848ae3378550350d88585a7cc5762cc2fb51afd054793b10",
  "repeat/STRING/run/caprice.log": "11d26ea5082e6a8675215affe8381e55b8a0c57422b717dd4b112c8297118362",
  "repeat/STRING/run/printer.dat": "179686fc37902ac7ec8d3cbf3997cbd4d032fc28780c44ad31482e4b13e15e23",
  "repeat/STRING/run/screen.png": "b1377343e6a825eb5eef032c2847067400478480f0fbd67219d008e8bdf51bce",
  "repeat/V07/capture.json": "391dd2ec8d4b3a46082858bdbb57f30cdbee1d143172bbd48bba501d553f15b3",
  "repeat/V07/list/caprice.log": "6477129578c02a38ecdbc87cea930bae8fae973162f17f11fc288a063c9e73b0",
  "repeat/V07/list/screen.png": "25b5ec6d3396bf53c6cf0e766f4dda008e6f39bdd46b14d0c40b9d05ea2b3a1f",
  "repeat/V07/program.bin": "d56c9c6fe16f8766e3e565a09f6aa4a81447e306c45afd78dc21884df5887812",
  "repeat/V07/run/caprice.log": "3dc6478c957d3e14ceab0a9cb16db7b79e71acb0c43a96529986b3f26137cb5b",
  "repeat/V07/run/printer.dat": "9bd23b1b61e0d23061ee673bda828b2262cb56d41badb948b75e1f602175c869",
  "repeat/V07/run/screen.png": "cf63a2e7d147b77d598c1a577adcbb43aeb4ee716926d0f086a8953e3b07b037",
  "repeat/VMAX/capture.json": "4219c1d013ee2f7a2276c837eab305ed450c98d6f9d29a88ed4053696eb7d412",
  "repeat/VMAX/list/caprice.log": "0fe5a977e15a674d5b1b581f51c07bccbbd7e7cf049920cfed40cf0926e51af5",
  "repeat/VMAX/list/screen.png": "925b8b5ffc12f63f406e163e39af3e6d06a26da15b7be4639928e7905243c26f",
  "repeat/VMAX/program.bin": "2479172217b01d771aad88bef1bcf9d053d2af40987594923771c50064324f6f",
  "repeat/VMAX/run/caprice.log": "ebae13329d0d8c7fa90056c83e65e6bdfc6eced2f53fbe907d47012302d3ee25",
  "repeat/VMAX/run/printer.dat": "32ddfd7d493a41b8b85e364a9e1bbeacffd97e9527ca70248a3bf7a36d684a86",
  "repeat/VMAX/run/screen.png": "30a46e89c1adbe68c0bddf9efa3f1aa0c0e6f8dd9bcfdfe6d368447726e125b4",
  "repeat/VMIN/capture.json": "88cd3d9666e7f010c281b9d2c9a12db18402b8e9780887125accf8b18cf6d6b7",
  "repeat/VMIN/list/caprice.log": "72dfe545e4d9641d301aee358bbf2f757732f037e38c5cdd071b3b0bb79110e4",
  "repeat/VMIN/list/screen.png": "e2e69efc9eff4a5d674ea0612d8af8413aea3823ea6ce6ed59ebc8cd6e3072c6",
  "repeat/VMIN/program.bin": "4bdbbf5976a245ad8b7de081a146353c1f05124ccbde2ee9bb8b323223ca86ac",
  "repeat/VMIN/run/caprice.log": "b3c19dcdc4a67326b172361a8d108ba78e6f65fb4d51089583585701a31e067d",
  "repeat/VMIN/run/printer.dat": "84356f9b36de2d1746360fdd9b89d2b76f49a996d503124eba14bfa71979ca50",
  "repeat/VMIN/run/screen.png": "c8547b3b393a1362a69b11017479abfcfd7bb629a2cf0325dbf172281665858f",
  "repeat/VN7/capture.json": "3c9651abc25d40174c5660a1f936f2909c2dd25db8bff92a5b96fc01e8f44e5a",
  "repeat/VN7/list/caprice.log": "2cee859cb4f1113cad5a7daf1021f75af183b878645153ff4193ecc4eca83c22",
  "repeat/VN7/list/screen.png": "50357dfbcfb5569be3a3b932b12890e52e9a27b92ea7eb0ec470ec9b865e2649",
  "repeat/VN7/program.bin": "5d3a15a7b0b79ee60232134caa7152125e038812437820d8872a116b129f9caf",
  "repeat/VN7/run/caprice.log": "9c84e054aead1f103fe10759357d39d8bc098ddf0107ab6f9502116d372849d6",
  "repeat/VN7/run/printer.dat": "9bd23b1b61e0d23061ee673bda828b2262cb56d41badb948b75e1f602175c869",
  "repeat/VN7/run/screen.png": "3dd875ec689062056fb286031fa55ce8a2bbc1936b20161afbec5fb7f1ea0d59",
  "repeat/VNMAX/capture.json": "d8472c730d2b6e8686bb3048dd710a579d703dd393b1b45a6cc376fab85a062d",
  "repeat/VNMAX/list/caprice.log": "022f2fe6e2fd5909e63cff557c420e82cf71e8cd99951668774f4f200ec1718a",
  "repeat/VNMAX/list/screen.png": "027771f87eafd6ac6913de584ff8fc4f5465eb5d580e1f56668684e4590fa116",
  "repeat/VNMAX/program.bin": "ebb7e192d639a604d7b255d17cf161b55caa4c3f0e5bed3a05eaeaa228beb34c",
  "repeat/VNMAX/run/caprice.log": "986563d9cddc0259d6d7225f88b7e4bacc2f4e59cd9f5995a8407316fec34ac7",
  "repeat/VNMAX/run/printer.dat": "32ddfd7d493a41b8b85e364a9e1bbeacffd97e9527ca70248a3bf7a36d684a86",
  "repeat/VNMAX/run/screen.png": "5b01ac03e33faa5115c965ee80d00b2387dd946764f3a13488100e404c7d6bd5"
}
ACQUISITION_HEAD='a37b27befe5a6b66aa0bfd4b68abdd26c429c07f'
SCREEN_SENTINEL=b'@@ABS-SCREEN@@'
ERR_SENTINEL=b'@@ABS-ERR@@'
SETUP=['MODE 1','NEW']

class Invalid(ValueError): pass
def check(ok,why):
    if not ok: raise Invalid(why)
def read(p):
    check(p.is_file() and not p.is_symlink(),'MISSING_'+str(p))
    return p.read_bytes()
def sha(data): return hashlib.sha256(data).hexdigest()
def enc(x): return (json.dumps(x,sort_keys=True,indent=2)+'\n').encode('ascii')
def source(case):
    expected=CASES[case].encode('ascii')
    check(read(SOURCES/(case.lower()+'.bas'))==expected,'SOURCE_DRIFT_'+case)
    return expected
def rows(case):
    return [int(line.split(' ',1)[0]) for line in CASES[case].splitlines()]
def png_ok(raw):
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'): return False
    pos=8; found=False
    while pos+12<=len(raw):
        length=int.from_bytes(raw[pos:pos+4],'big')
        kind=raw[pos+4:pos+8]
        end=pos+12+length
        if end>len(raw): return False
        got=int.from_bytes(raw[end-4:end],'big')
        if zlib.crc32(raw[pos+4:end-4])&0xffffffff!=got: return False
        pos=end
        if kind==b'IEND':
            found=True;break
    return found and pos==len(raw)

def snapshot_program(snapshot):
    check(len(snapshot)==cpc.HEADER+cpc.RAM_BYTES,'SNA_SIZE')
    ram=memoryview(snapshot)[cpc.HEADER:]
    start=cpc.u16(ram,cpc.PROGRAM_BASE_PTR)+1
    end=cpc.u16(ram,cpc.PROGRAM_END_PTR)
    check(0x170<=start<end<=0x8000,'PROGRAM_POINTERS')
    data=bytes(ram[start:end])
    numbers,_=cpc.records(data)
    validated,region=cpc.extract_snapshot(snapshot,numbers)
    check(data==validated,'SNA_EXTRACTION')
    return data,region,numbers

def check_head(head):
    check(bool(re.fullmatch('[a-f0-9]{40}',head)),'INVALID_HEAD')
    actual=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    check(head==actual,'EXPECTED_HEAD_MISMATCH')
    return head

def capture_one(cap,out,case,session,tmp):
    src=source(case)
    work=out/session/case
    lsnap=tmp/(case+'-'+session)
    lsnap.mkdir()
    initial=SETUP+src.decode('ascii').splitlines()
    list_commands=initial+['LIST','CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT']
    lt=ink.launch(cap,work/'list',lsnap,list_commands,False)
    snapshots=list(lsnap.glob('*.sna'))
    check(len(snapshots)==1,'SNA_MISSING_'+case+session)
    program,region,found=snapshot_program(read(snapshots[0]))
    (work/'program.bin').write_bytes(program)
    # Program result is printed both on-screen and to the CPC #8 printer
    # by the SOURCE itself. The post-RUN ERR/ERL probe is separate.
    # Screen extraction is performed AFTER the screenshot and ERR/ERL probe,
    # with COPYCHR$ (#0) from the CPC firmware, not desktop OCR.
    run_commands=initial+['RUN','CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                          'PRINT #8,"@@ABS-ERR@@";ERR;",";ERL',
                          'PRINT #8,"@@ABS-SCREEN@@"',
                          'FOR YY=1 TO 25:FOR XX=1 TO 40:LOCATE XX,YY:PRINT #8,COPYCHR$(#0);:NEXT XX:PRINT #8:NEXT YY',
                          'CAP32_DELAY CAP32_EXIT']
    rt=ink.launch(cap,work/'run',tmp,run_commands,True)
    raw=read(work/'run/printer.dat')
    idx=raw.find(ERR_SENTINEL)
    check(idx>=0,'ERR_ERL_MARKER_MISSING_'+case+session)
    prefix=raw[:idx]
    tail=raw[idx+len(ERR_SENTINEL):]
    match=re.match(rb'\s*([0-9]+)\s*,\s*([0-9]+)\s*[\r\n]+',tail)
    check(match is not None,'ERR_ERL_NUMERIC_PROBE_'+case+session+repr(tail[:120]))
    err=int(match.group(1));erl=int(match.group(2))
    screen_pos=tail.find(SCREEN_SENTINEL,match.end())
    screen_text=tail[screen_pos+len(SCREEN_SENTINEL):] if screen_pos>=0 else b''
    lines=screen_text.splitlines()
    screen_class='TEXT_SCREEN_OBSERVED' if len(lines)==25 else 'DIAG_CPC_UNVERIFIED'
    case_class='INPUT_REJECTED' if found!=rows(case) else 'OBSERVED'
    rec={'case':case,'session':session,'source_sha256':sha(src),
         'line_numbers_requested':rows(case),'line_numbers_observed':found,
         'input_classification':case_class,'token_classification':
          'TOKEN_UNVERIFIED' if case_class!='OBSERVED' else 'OBSERVED',
         'program_sha256':sha(program),'program_hex':program.hex(' ').upper(),
         'region':region,'run_printer_sha256':sha(raw),
         'result_printer_hex':prefix.hex(' ').upper(),
         'err':err,'erl':erl,'list':lt,'run':rt,
         'list_image_sha256':sha(read(work/'list/screen.png')),
         'run_image_sha256':sha(read(work/'run/screen.png')),
         'screen_text_hex':screen_text.hex(' ').upper(),
         'screen_text_classification':screen_class,
         'screen_rows':len(lines),
         'diagnostic_classification':'DIAG_CPC_UNVERIFIED',
         'type_classification':'TYPE_UNVERIFIED',
         'setup_commands':SETUP,'list_commands':list_commands,
         'run_commands':run_commands,'printer_is_not_screen_evidence':True,
         'snapshot_before_run':True,'full_snapshot_archived':False}
    (work/'capture.json').write_bytes(enc(rec))
    print(PHASE,case,session,'INPUT',case_class,'RAM',program.hex(' ').upper(),
          'RESULT',prefix.hex(' ').upper(),'ERR',err,'ERL',erl,
          'SCREEN_ROWS',len(lines),flush=True)
    return rec

def acquire(cap,out,head):
    check(not out.exists(),'OUTPUT_EXISTS')
    version=ink.check_caprice(cap)
    out.mkdir(parents=True)
    manifest={'schema_version':1,'phase':PHASE,'acquisition_head':head,
              'run_id':os.environ.get('GITHUB_RUN_ID','LOCAL'),
              'oracle':{'caprice':cpc.PIN,'rom':cpc.ROM_SHA,
                        'ghcr':GHCR,'version':version,
                        'model':'CPC6128','basic':'1.1'},
              'native_changes':False,'full_snapshots_archived':False,'cases':{}}
    with tempfile.TemporaryDirectory(prefix='j120-abs-sna-') as tmp:
        t=Path(tmp)
        for case in CASES:
            observed={}
            for session in SESSIONS:
                observed[session]=capture_one(cap,out,case,session,t)
            check(observed['original']['program_hex']==observed['repeat']['program_hex'],
                  'INDEPENDENT_RAM_MISMATCH_'+case)
            check((observed['original']['err'],observed['original']['erl'],
                   observed['original']['result_printer_hex'])==
                  (observed['repeat']['err'],observed['repeat']['erl'],
                   observed['repeat']['result_printer_hex']),
                  'INDEPENDENT_RUN_MISMATCH_'+case)
            manifest['cases'][case]={s:sha(read(out/s/case/'capture.json'))
                                     for s in SESSIONS}
    (out/'manifest.json').write_bytes(enc(manifest))
    verify(out)
    print(PHASE,'FRESH_CPC_SESSIONS',2*len(CASES),'UNSEALED',head,flush=True)

def verify(out,permanent=False):
    m=json.loads(read(out/'manifest.json'))
    check(m['phase']==PHASE and m['schema_version']==1 and
          m['oracle']['caprice']==cpc.PIN and m['oracle']['rom']==cpc.ROM_SHA and
          m['oracle']['ghcr']==GHCR and m['native_changes'] is False and
          m['full_snapshots_archived'] is False and
          set(m['cases'])==set(CASES) and
          bool(re.fullmatch('[a-f0-9]{40}',m['acquisition_head'])),
          'MANIFEST_PROVENANCE')
    check(subprocess.run(['git','-C',str(ROOT),'merge-base','--is-ancestor',
                          m['acquisition_head'],'HEAD'],capture_output=True).returncode==0,
          'FALSE_ACQUISITION_HEAD')
    inventory={str(p.relative_to(out)):sha(read(p)) for p in out.rglob('*') if p.is_file()}
    check('manifest.json' in inventory,'MISSING_MANIFEST')
    if permanent:
        check(m['acquisition_head']==ACQUISITION_HEAD and
              sha(read(out/'manifest.json'))==SEALED_MANIFEST and
              bool(SEALED) and set(SEALED)==set(inventory)-{'manifest.json'},
              'EXTERNAL_MANIFEST_OR_INVENTORY')
        for key,digest in SEALED.items():
            check(inventory[key]==digest,'EXTERNAL_FILE_SHA_'+key)
    for case in CASES:
        pair=[]
        for session in SESSIONS:
            work=out/session/case
            recdata=read(work/'capture.json')
            d=json.loads(recdata)
            program=read(work/'program.bin')
            raw=read(work/'run/printer.dat')
            found,details=cpc.records(program)
            expected_class='OBSERVED' if found==rows(case) else 'INPUT_REJECTED'
            check(d['source_sha256']==sha(source(case)) and
                  d['program_sha256']==sha(program) and
                  d['program_hex']==program.hex(' ').upper() and
                  d['line_numbers_observed']==found and
                  d['line_numbers_requested']==rows(case) and
                  d['input_classification']==expected_class and
                  d['token_classification']==('OBSERVED' if expected_class=='OBSERVED' else 'TOKEN_UNVERIFIED') and
                  d['snapshot_before_run'] and not d['full_snapshot_archived'] and
                  d['setup_commands']==SETUP and d['case']==case and d['session']==session and
                  sha(recdata)==m['cases'][case][session],
                  'CASE_PROVENANCE_'+case+session)
            for kind in ('list','run'):
                png=read(work/kind/'screen.png')
                log=read(work/kind/'caprice.log')
                check(png_ok(png) and log.startswith(b'exit code: 0\n') and
                      d[kind]['screenshot_width']==int.from_bytes(png[16:20],'big') and
                      d[kind]['screenshot_height']==int.from_bytes(png[20:24],'big') and
                      sha(png)==d[kind+'_image_sha256'],
                      'PNG_CRC_OR_PROCESS_'+case+session+kind)
            check(sha(raw)==d['run_printer_sha256'] and
                  d['diagnostic_classification']=='DIAG_CPC_UNVERIFIED' and
                  d['type_classification']=='TYPE_UNVERIFIED',
                  'UNVERIFIED_CLAIM_OR_PRINTER_'+case+session)
            idx=raw.find(ERR_SENTINEL)
            check(idx>=0 and d['result_printer_hex']==raw[:idx].hex(' ').upper(),
                  'PRINTER_RESULT_'+case+session)
            match=re.match(rb'\s*([0-9]+)\s*,\s*([0-9]+)\s*[\r\n]+',
                           raw[idx+len(ERR_SENTINEL):])
            check(match is not None and
                  (int(match.group(1)),int(match.group(2)))==(d['err'],d['erl']),
                  'ERR_ERL_'+case+session)
            if expected_class!='OBSERVED':
                check(d['token_classification']=='TOKEN_UNVERIFIED','FALSE_TOKEN_CLAIM')
            pair.append(d)
        check(pair[0]['program_hex']==pair[1]['program_hex'] and
              (pair[0]['err'],pair[0]['erl'],pair[0]['result_printer_hex'])==
              (pair[1]['err'],pair[1]['erl'],pair[1]['result_printer_hex']),
              'INDEPENDENT_PAIR_'+case)
    print(PHASE,'VERIFIED',len(CASES)*2,
          'SESSIONS','EXTERNAL' if permanent else 'UNSEALED',flush=True)

def negatives(out,permanent=False):
    originals={str(p.relative_to(out)):sha(read(p)) for p in out.rglob('*') if p.is_file()}
    for kind in ('ram','list','run','printer','diagnostic','manifest','head','missing','pair','coordinated'):
        with tempfile.TemporaryDirectory(prefix='j120-falsification-') as tmp:
            clone=Path(tmp)/'clone'
            shutil.copytree(out,clone)
            work=clone/'original/A00'
            c=work/'capture.json'
            if kind in ('ram','coordinated'):
                p=work/'program.bin';v=bytearray(read(p));v[4]^=1;p.write_bytes(v)
                if kind=='coordinated':
                    d=json.loads(read(c));d['program_sha256']=sha(v);d['program_hex']=v.hex(' ').upper()
                    c.write_bytes(enc(d));m=json.loads(read(clone/'manifest.json'))
                    m['cases']['A00']['original']=sha(read(c))
                    (clone/'manifest.json').write_bytes(enc(m))
            elif kind in ('list','run'):
                p=work/kind/'screen.png';v=bytearray(read(p));v[-20]^=1;p.write_bytes(v)
            elif kind=='printer':
                p=work/'run/printer.dat';v=bytearray(read(p));v[0]^=1;p.write_bytes(v)
            elif kind=='diagnostic':
                d=json.loads(read(c));d['err']=999;c.write_bytes(enc(d))
            elif kind=='manifest':
                m=json.loads(read(clone/'manifest.json'));m['native_changes']=True
                (clone/'manifest.json').write_bytes(enc(m))
            elif kind=='head':
                m=json.loads(read(clone/'manifest.json'));m['acquisition_head']='0'*40
                (clone/'manifest.json').write_bytes(enc(m))
            elif kind=='missing':(work/'program.bin').unlink()
            elif kind=='pair':
                p=clone/'repeat/A00/program.bin';v=bytearray(read(p));v[4]^=1;p.write_bytes(v)
            try:verify(clone,permanent)
            except (Invalid,ValueError,KeyError,OSError,IndexError):
                print(PHASE,'FALSIFICATION_REJECTED',kind,flush=True)
            else:raise Invalid('FALSIFICATION_ACCEPTED_'+kind)
    for rel,digest in originals.items():
        check(sha(read(out/rel))==digest,'ARCHIVE_CHANGED_'+rel)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--check-sources',action='store_true')
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--permanent',action='store_true')
    p.add_argument('--expect-head')
    p.add_argument('--caprice',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--evidence',type=Path)
    a=p.parse_args()
    if a.expect_head:check_head(a.expect_head)
    if a.check_sources or a.self_test:
        for name in CASES:source(name)
        check(len(CASES)>=12 and len(SESSIONS)==2,'INSUFFICIENT_MATRIX')
        cpc.self_test()
        print(PHASE,'16_CASE_SOURCES_CHECKED',flush=True)
    if a.caprice:
        check(a.output is not None,'OUTPUT_REQUIRED')
        head=check_head(a.expect_head or subprocess.check_output(
            ['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip())
        acquire(a.caprice.resolve(),a.output.resolve(),head)
    if a.evidence:
        verify(a.evidence.resolve(),a.permanent)
        if a.self_test:negatives(a.evidence.resolve(),a.permanent)
    else:
        check(not a.permanent,'PERMANENT_REQUIRES_ARCHIVE')
    check(a.check_sources or a.self_test or a.caprice or a.evidence,'NO_ACTION')

if __name__=='__main__':
    try:main()
    except (Invalid,ValueError,OSError,subprocess.SubprocessError,KeyError,IndexError,UnicodeError) as exc:
        print(PHASE,'FAIL',str(exc),file=sys.stderr)
        sys.exit(1)
