#!/usr/bin/env python3
"""J1.19-A: independent CPC6128 PAPER acquisition/verification; no native PAPER.

IMPORTANT: Until actual Caprice32 observations and OUT-OF-ARCHIVE SHA pins
exist, --permanent deliberately refuses ALL archives. No simulated CPC facts.
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
SOURCES = ROOT / 'tests/oracles/inputs/j1_19_a'
PHASE = 'J1.19-A'
SESSIONS = ('original', 'repeat')
BASIC = {
    'P00': '0', 'P01': '1', 'P02': '2', 'P03': '3',
    'P04': '4', 'P15': '15', 'P16': '16', 'PN1': '-1',
}
SCENARIOS = {
    'SPRINT': ('10 PAPER 2', '20 LOCATE 1,15', '30 PRINT "J119TEST"', '40 END'),
    'SCHANGE': ('10 PAPER 0', '20 LOCATE 1,15', '30 PRINT "J119OLD"',
                '40 PAPER 2', '50 LOCATE 1,16', '60 PRINT "J119NEW"', '70 END'),
    'SCLS': ('10 PAPER 3', '20 CLS', '30 LOCATE 1,15', '40 PRINT "J119TEST"', '50 END'),
    'SINK': ('10 INK 2,6', '20 PEN 1', '30 PAPER 2', '40 LOCATE 1,15',
             '50 PRINT "J119TEST"', '60 END'),
}
CASES = tuple(BASIC) + tuple(SCENARIOS)
GHCR = ('ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:'
        '7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c')
ROM_SHA256 = '31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562'
CAPRICE_COMMIT = '8c778bf072a06fb7c23b9cccd179041db7f79a52'
# SEALED VALUES MUST COME FROM AN INDEPENDENT REAL ACTIONS ACQUISITION,
# fixed outside manifest, checked against the original external artifact.
# Never compute these from the current directory being verified.
SEALED_MANIFEST_SHA256 = '1c43f4aac125b8213ae878944a9940d13741adc74e32692a2914a6b83bb532b2'
SEALED_ACQUISITION_PARENT = 'cf6cc1b5fc07ef7d0310c297ee4043bd78568d94'
SEALED_FILE_SHA256 = {
    "original/P00/baseline/caprice.log": "875d347520158b40da9a3222789ce47e40f2e95b47be7cc0683d3b64bec19917",
    "original/P00/baseline/screen.png": "9c11004b03e4848687cabd983a41516ef7ea4c321c56f7a4d41db48beed352a9",
    "original/P00/capture.json": "37ed324315da5741eb049d7def5f9879396973ebbf49fc2a506aa7f0a733abc9",
    "original/P00/list/caprice.log": "d07a4361c8b699e7857631393725c1afbec7c5dbf563cbc3f9d485d787fa4530",
    "original/P00/list/printer.dat": "cc39e52a0327bc0df134453ed11e6ea4112b62c97e3999eb5444e9cabfd43728",
    "original/P00/list/screen.png": "9a08c8534dde0a98278b94fbd2f441484ec4aa461711523d075ef46ad0c2ef8e",
    "original/P00/program.bin": "2fc54e4bfd60b3a8a38c80daecd26077602f47376d2744da1757d3df76342d47",
    "original/P00/run/caprice.log": "ed377375252351e3c1043f0170dcad1846514095aec3cf54fea314f939d78c41",
    "original/P00/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/P00/run/screen.png": "eeac1b23b2f4f616f0089f4d3f6c220f9b78933c22e847bb462a9f86b5e351bb",
    "original/P01/baseline/caprice.log": "bac4c5debd25fd3b0e68efbe2e64fae3271a45eab02acbe617d03231784c51e5",
    "original/P01/baseline/screen.png": "9c11004b03e4848687cabd983a41516ef7ea4c321c56f7a4d41db48beed352a9",
    "original/P01/capture.json": "80085204520fc6adde4132da83fcd17398047f005014c5552877dc2a6fcadb96",
    "original/P01/list/caprice.log": "ec27816d3866c891c7fda180791fbeeaeba5d47cce2f58da9fe561426934d5e6",
    "original/P01/list/printer.dat": "7fa26f379dfb05b5d9fd9619b37710c4235018a22bb082c160a98d8b0e565803",
    "original/P01/list/screen.png": "2d00e9fd905927519e4a2e197772c5f9b17adfa066e5d2909a38c6a2a51bc4fd",
    "original/P01/program.bin": "7277311c1fa417c2277efe3cbb4f88b412081b04d33550a8df1702acfe77c056",
    "original/P01/run/caprice.log": "4f548ef326fd39b4501b15b7f094600697184c0b472f600cf3b3b1bdf2dd79d8",
    "original/P01/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/P01/run/screen.png": "916c27f536492db22b73af368345661f8d2d331eb251e6b80eeb8d365138b4c3",
    "original/P02/baseline/caprice.log": "aee30e833443744eb9c68290dbb5470e9bb2c89ead45fbcc684507f375b690fe",
    "original/P02/baseline/screen.png": "6234af66576df2bc7e731bfc9950be0325ae2b2f51c9535d231a40b19ad645a6",
    "original/P02/capture.json": "4a86a2e04c9f300d1cfa54768f99ba4f87d0c2f8a497884554a7221d301b7fc1",
    "original/P02/list/caprice.log": "9b8cd1522d9ed292b9cdcc9c98a0f184e9133bb48ff68dc09988b6d82b91437c",
    "original/P02/list/printer.dat": "b9873704fefefea35faadd70aeaa3aa86a55cf94476dd77322aed7368384856c",
    "original/P02/list/screen.png": "5ba0ee889a3fd08895c33f509f5178ce542b5232b6028417e1fff8825e0a8d8f",
    "original/P02/program.bin": "94004f0506878fb65d085704794e2b23ff94cb3373cb921ed638018ed3f84cd9",
    "original/P02/run/caprice.log": "13ef4e1ceb6cd32ba04abb012f9b6c5a9badf80264b6bfbb496fcc00374886a3",
    "original/P02/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/P02/run/screen.png": "9a77127c84f4e2b4f428b90e02c326f6dcd613c4abb5fd1c1215b39bc12e8c73",
    "original/P03/baseline/caprice.log": "a47797a492dd3c79b89bbef61ecd5394c6ed84b5e7aeea8b472f852c552f7fb2",
    "original/P03/baseline/screen.png": "f5f21a05e20747c34eb264d1462b53618598247fa868725b5f352e1ff84ea019",
    "original/P03/capture.json": "403087df3d536f30e872c6c0680a0f06385d7f04417e92e15f8ac4d1c0395401",
    "original/P03/list/caprice.log": "0f52b5c620a0526d75060231cc28fc184faa0af0d4fc9489e93a64a574aa1afa",
    "original/P03/list/printer.dat": "b4cb51ca1a6b63fdc8e8d25ff45e07faaee295ffed24244338250b2d644845f5",
    "original/P03/list/screen.png": "2e39eb48a49ad7e4c1ba2f4ceb84376e054e3eae8430ff89742cd0c38a542a3e",
    "original/P03/program.bin": "b9e7018bf2a02514eb0573665c130d2740ad959324cc39714d064d00697882db",
    "original/P03/run/caprice.log": "c235ca9d7150c6c4b3e00f3310964ec55ce2b1898ae631a2bb3a9512e7f897e0",
    "original/P03/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/P03/run/screen.png": "0da462f8f24ddbadb7985036d33fbb6b979bbe596f8a3cef0daa6aeaa06c5f2f",
    "original/P04/baseline/caprice.log": "4bf13efa85f66a1744de546c26b282d7a6779210b7c8a7546eaa2d48e4194b1e",
    "original/P04/baseline/screen.png": "9c11004b03e4848687cabd983a41516ef7ea4c321c56f7a4d41db48beed352a9",
    "original/P04/capture.json": "e356f91379044de3f96927cac3f3f30461968e302067137e45eb04a1428f0b89",
    "original/P04/list/caprice.log": "14e0e4c8171d79c776b1f87b523357348f2ad7be66f0958d55c93a09f6e83354",
    "original/P04/list/printer.dat": "7b7a1af78c2bb89bc174012ecdc23e152583137b63161b8caa78a799c9d3bb28",
    "original/P04/list/screen.png": "14aefd821cdaf4d26a488b36ef545c88ea8b8b1865ef4e1c5d1d60935715d5f6",
    "original/P04/program.bin": "ae65fefb678d48ec46c6ddf83d9867c8c3cbce2159527d3d0c1de64e7585a5cb",
    "original/P04/run/caprice.log": "1ff0fc0a1b5ba789c2cb5b11c7c3e3fdc2d5b540ee28d218c1f84895334c17e4",
    "original/P04/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/P04/run/screen.png": "06900060ffe3951acd6cb96dc2ed843b907e0f494c166a3070b5fd2c80b798c7",
    "original/P15/baseline/caprice.log": "148f36b664c67d81d65be94600c2997a29b98bf78834067c19db628c312504ae",
    "original/P15/baseline/screen.png": "f5f21a05e20747c34eb264d1462b53618598247fa868725b5f352e1ff84ea019",
    "original/P15/capture.json": "827368fbdc5a54edf7b8072b332de6d728671a83a9abec197c35bd3c8ff74fa8",
    "original/P15/list/caprice.log": "2e9142f846685e4aa2f2e3ec9f34ef8b7f243940b58bf72ba67e75ecad52673d",
    "original/P15/list/printer.dat": "57cdc12820f7dd4969a930d407cc93e884923e7cd8d6c52d53b5654f94908544",
    "original/P15/list/screen.png": "41f8343a49c6a3f7b5f7778405b8c873c8b8b06c708374cbfc7d0d5d2460f391",
    "original/P15/program.bin": "60923aed7048424af2b10b2a4fad12ece35dd1754b189a7391b815dc5bc5384d",
    "original/P15/run/caprice.log": "3e7fa9c86d2b3a6b5831ce4e3f0886ee4d077c944eaa0dce62ad613712135aef",
    "original/P15/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/P15/run/screen.png": "afa0a87092587cd7259b86a3d47f8acd82f2d48b177ad76c231940f002e8c0d1",
    "original/P16/baseline/caprice.log": "f020acda9318e0f1000e6257b50a21d2217b9e66b03a46af85500f122b2a5527",
    "original/P16/baseline/screen.png": "1da0f5f557de0bf381f05d68980c8f52694b888ac1ba5c8accdf8e71786ed691",
    "original/P16/capture.json": "833868e2844466cc99145510060ff73cb675c4a71db0a120ae9e981449f18a1d",
    "original/P16/list/caprice.log": "e77f04c467b7a092246722238fc8a384bc1eda187cf6a7659ad746894e05b411",
    "original/P16/list/printer.dat": "2e487baa1f6eb1693f51c0b6e3a1eb3fb8d15d22e168d0f01a44d2233b61a3bf",
    "original/P16/list/screen.png": "fb3b63c72b9c5743815bb24af6834ff839e6923965d2d2e0ee15dcddb21f214d",
    "original/P16/program.bin": "c997bdf177482cc4d9707ed63a5f3eb9db28edc58aa568d7940d99c6c083d9ed",
    "original/P16/run/caprice.log": "4b83854f3d3cb54c5d099c04ebac72e404391c4976cb14a51c3c4ecb9e7df52a",
    "original/P16/run/printer.dat": "d339b4cf87335e2e86603aae9b87935df5a97dd981f0edd464b214b3c4cb15db",
    "original/P16/run/screen.png": "887d6ff2fb7d92e2d1708e463f4a884e776edb8432ca315e366cb0c25fa51a00",
    "original/PN1/baseline/caprice.log": "7cd35cb8c42a186a7c24f09d0e02a54078c64e0294ff669549d2771574299e05",
    "original/PN1/baseline/screen.png": "9c11004b03e4848687cabd983a41516ef7ea4c321c56f7a4d41db48beed352a9",
    "original/PN1/capture.json": "3bcd9553b071e2fabe2a2fa481fafd5f33a5c00fabbabc66675ce265f6b01949",
    "original/PN1/list/caprice.log": "2c3bab42b87ae36e78acdbb5df927253be56742ca354c1921364317e81406c03",
    "original/PN1/list/printer.dat": "b6cb9fad5366a6caa7310e533b795ce68add3daae7665d4ad7b92ebc238788e8",
    "original/PN1/list/screen.png": "5c5a6ea962e1206cdccf639ea9c355fa3985f7ce20261d6e9e19e50839c89278",
    "original/PN1/program.bin": "db6d2173311f67ef4c36a6e2e4a82cddb94930cdfbf5705edb96edcd400a4825",
    "original/PN1/run/caprice.log": "72c21fb23df9ffc0fe12619216d8f1baf3b0770268ddbab6421a9fe9b8b768aa",
    "original/PN1/run/printer.dat": "d339b4cf87335e2e86603aae9b87935df5a97dd981f0edd464b214b3c4cb15db",
    "original/PN1/run/screen.png": "ce370a18d99fb7b0aebc3b96f6d3622f622889e147ba91d387a41bc27b988139",
    "original/SCHANGE/baseline/caprice.log": "c117c0a8235c2bc397396ea3ca2013442e7740919956f0bae4592ccc516a46ce",
    "original/SCHANGE/baseline/screen.png": "9c11004b03e4848687cabd983a41516ef7ea4c321c56f7a4d41db48beed352a9",
    "original/SCHANGE/capture.json": "f57e0d7f899d895a97bf4377d416639e68bea712eb21214602817665475bde5b",
    "original/SCHANGE/list/caprice.log": "7c873961e0c93cc9717d48a45e11b2089a557241740185ae63851aa5ee265eea",
    "original/SCHANGE/list/printer.dat": "ce5bda694db29128de8475c9d11efe609ad2bc0fab11375afc0635f0de8fc15b",
    "original/SCHANGE/list/screen.png": "52f80f2a031f8854a1c7d36bad6512203e201c6b3d10f1af3dd4dc0aed95fd6d",
    "original/SCHANGE/program.bin": "2221c9775f56e62485e215fe9e75378c8db380591db6448dd97175fb7b603078",
    "original/SCHANGE/run/caprice.log": "ce1bb19f3d74557ed56eecde84d2f04a2248bcbe3e2be0ed409fe1639dc08376",
    "original/SCHANGE/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/SCHANGE/run/screen.png": "2546a3c36ad514f329fb5fa6f0030f675d1340afb8a6fef696495b5392564afe",
    "original/SCLS/baseline/caprice.log": "dabe268284100de9e77bbd45b75ed3af524eb2bbbce472947dc36494803fbf44",
    "original/SCLS/baseline/screen.png": "5e8fdf75df94df52edb65169fb682bd96a4f73293e99945ddd7f5127f2ee806f",
    "original/SCLS/capture.json": "e76a8faedd4bcfae8d59931b951e3bf39f3e115f8b654cfa0620a00a0c09e0c6",
    "original/SCLS/list/caprice.log": "5f29d8f8d55ba355c114ba1e408706a8b6c41038fc508e3dc6a0275b34ac0cc7",
    "original/SCLS/list/printer.dat": "dc247e51dbfc1aa1e1fa2d36448044abe62e3d83e82a741d3c7375f1a533e4fd",
    "original/SCLS/list/screen.png": "d1d54ba7dda43e98efb29b0842a1bf1c54823f10a7ab108fb2e14c5dc6ca3af3",
    "original/SCLS/program.bin": "336394c3f9e0cc54767ff51443d00752d6447ff3dd82eabdc3be9517839eedf9",
    "original/SCLS/run/caprice.log": "a34ee2de4f473a9094572d5118eeeb9397de771642795b596328dc1944b01dc7",
    "original/SCLS/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/SCLS/run/screen.png": "86ac52a4e6ae8ea690987633b225055e8cdd266a121622ed18677777e65e35c9",
    "original/SINK/baseline/caprice.log": "2842eb8aa62f0c651747bfc49e6b19c7875cb88e359be737feae39c80a18e692",
    "original/SINK/baseline/screen.png": "5e8fdf75df94df52edb65169fb682bd96a4f73293e99945ddd7f5127f2ee806f",
    "original/SINK/capture.json": "d0376e54308fd4565c899369b8b6a7afdfd0db24425692c464897d56c5296d13",
    "original/SINK/list/caprice.log": "28a059957d4c561f11563a70f71ea7f0b8e6a64119584d19b5713c4f17faa8ee",
    "original/SINK/list/printer.dat": "f714eb314991c526a537253f117feb8fec72b4aad7d63adc8100e91cb192b7f7",
    "original/SINK/list/screen.png": "46bd2496d035575212ed767c00f62f55a65dad24747db58aa7f53ff5d3c56fe7",
    "original/SINK/program.bin": "7b4e1b07d46b625099a3ed14d8fa8ee9295e57427fabee324a3436aadea0fdb4",
    "original/SINK/run/caprice.log": "0ba02633b2b4be9fc06f949cff16a9a8da26c0e4c215433ab9ab0f81e8415d75",
    "original/SINK/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/SINK/run/screen.png": "f6a972b917132da67fff3ea65c38c48bc7c2b98ef6b1f0997f03e0dfa726b693",
    "original/SPRINT/baseline/caprice.log": "487243bd0a19ee365714b6adf9fc9fcc8a66465093bcfc9e4db42a7152756684",
    "original/SPRINT/baseline/screen.png": "f5f21a05e20747c34eb264d1462b53618598247fa868725b5f352e1ff84ea019",
    "original/SPRINT/capture.json": "7cc59e654097084f75db671e40e5d676562c7ad14db623ade76bd7c6ab2094e3",
    "original/SPRINT/list/caprice.log": "bbdb1830c2b892fd913e4f41c072e6708abee8b871739fe465cebec0dad482d2",
    "original/SPRINT/list/printer.dat": "a7fd9cbfc4c4300c54ecffda8949e051bc32bce438a8cb4b6d8c3907ddddf282",
    "original/SPRINT/list/screen.png": "cd8ecf6cf86da11fc61b3eb18e998f0da2cf8b776aad1dd818b5a6506cc6544d",
    "original/SPRINT/program.bin": "758641f723ed91ca4e87e42bb57dfa3efc2b7d891f2df40886ac8ee5aff9895b",
    "original/SPRINT/run/caprice.log": "c45540c1d3e3e02b5e39d05eb68f06066b4fa89408f9a4ff8715ef7afdb9422a",
    "original/SPRINT/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "original/SPRINT/run/screen.png": "254f91196c944bef690232d3fcd49159ada05149047ab2bb7e024687c8e9605d",
    "original/chronology/caprice.log": "911e7a51a9a24174e7ac1f566d284be31f476403e49229da22570c356dbe18ac",
    "original/chronology/capture.json": "a4460a2df82092388f7bb4741f9a83dfc4e54b6505b097ade27177312651bbd6",
    "original/chronology/screen_0.png": "968a2c9e4b238f626eab7382fffd87c17e518c7b4c8cee1d1b9aef77ab738d6b",
    "original/chronology/screen_1.png": "d620f25dbe9126245967eed1e1a8126d8780e097e837cf3193ea1f06774df6ec",
    "original/direct/D16/caprice.log": "a8491b32604947812ac7a1adf3eab13997fdd5c859fec4e0f06520cbfc7897f1",
    "original/direct/D16/capture.json": "905dfd6f9e522919e30b477c4b824f804749a73f9e539f7832cc98b0ddf9680a",
    "original/direct/D16/printer.dat": "16369e608df84ec5e441306ef7e915d640ad81bd0796bf3ec2e0c901b190b37b",
    "original/direct/D16/screen.png": "d690dc58c71b2fbdbbb715aad45ecff0da2277cc228b3a28010eb1c2f090aa3b",
    "original/direct/DN1/caprice.log": "914453c312783ce89719fb71820e75c819af0029f24787c4e1110725fedffc90",
    "original/direct/DN1/capture.json": "c2f2a4d33c47a918ced9a422da638b8f432346dfbfd0e415d549e7f465a04974",
    "original/direct/DN1/printer.dat": "16369e608df84ec5e441306ef7e915d640ad81bd0796bf3ec2e0c901b190b37b",
    "original/direct/DN1/screen.png": "5b2cadf7a94cdd851f68c5b566fc39f135ba3c14fa4ba6abf711427d5a2d7310",
    "repeat/P00/baseline/caprice.log": "21174b747338ca5d2206553221f4fa933ead0112f49144a16612d75f70c64e64",
    "repeat/P00/baseline/screen.png": "1da0f5f557de0bf381f05d68980c8f52694b888ac1ba5c8accdf8e71786ed691",
    "repeat/P00/capture.json": "fbd6b8e5377ee580699e2fcceab23398641a27a1922e9bf23980b254f8ed6abf",
    "repeat/P00/list/caprice.log": "264e9091800feabc939a66b788747743daf26b2046ed74b6a9f42154d5a6ec66",
    "repeat/P00/list/printer.dat": "cc39e52a0327bc0df134453ed11e6ea4112b62c97e3999eb5444e9cabfd43728",
    "repeat/P00/list/screen.png": "81fd71ca76fa71e5bddcbeef2457799a0c0b14a1ac6ba16cb7da5fdf64c4ad17",
    "repeat/P00/program.bin": "2fc54e4bfd60b3a8a38c80daecd26077602f47376d2744da1757d3df76342d47",
    "repeat/P00/run/caprice.log": "cf1ceda3c7b677cd951faa8382ea2c3163f6417c86a6ea7a498b4a4caab7dca5",
    "repeat/P00/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/P00/run/screen.png": "0e96da93f636eb251ef8cb6f4a82f6b2929ed97558c10e9fde766911d3fb36c6",
    "repeat/P01/baseline/caprice.log": "3a68d21ae40a111742bb7fbf96ed2c67efae85244fd562430b7ca7f9185cdef6",
    "repeat/P01/baseline/screen.png": "f5f21a05e20747c34eb264d1462b53618598247fa868725b5f352e1ff84ea019",
    "repeat/P01/capture.json": "8f237cf9d6248e36a903fc02025a861c25dc2c7e2f1057421821144db18aa841",
    "repeat/P01/list/caprice.log": "d552629b5c239fbaea75976c345c05da5e9682d98e63e0ce0f1338788a1dc35e",
    "repeat/P01/list/printer.dat": "7fa26f379dfb05b5d9fd9619b37710c4235018a22bb082c160a98d8b0e565803",
    "repeat/P01/list/screen.png": "db93570d02ed870c5200d715535774df8a1a0576a6a7d2744cb66dcf77a2481e",
    "repeat/P01/program.bin": "7277311c1fa417c2277efe3cbb4f88b412081b04d33550a8df1702acfe77c056",
    "repeat/P01/run/caprice.log": "f16bcdbad8f5bef7842f5b4d7e7f4f049e81151ea4f230fd217d0ef7cf709b87",
    "repeat/P01/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/P01/run/screen.png": "916c27f536492db22b73af368345661f8d2d331eb251e6b80eeb8d365138b4c3",
    "repeat/P02/baseline/caprice.log": "35be779c554f74a8c4d6b7be6da8fba9c50261dc7f165a3f84f49d196e01ccd3",
    "repeat/P02/baseline/screen.png": "47e256684d807aa0de2ea6ff4a145d356e241fed2398a7a8ffdbdc5ed029e667",
    "repeat/P02/capture.json": "cb12772b15a97099c06913e2e78e50bc49c71eda79fcd7e9dfb769ad612102b0",
    "repeat/P02/list/caprice.log": "57180e41e8889277befe17ccc025c70e4b8c57cfb83debb69795a43dfae07b17",
    "repeat/P02/list/printer.dat": "b9873704fefefea35faadd70aeaa3aa86a55cf94476dd77322aed7368384856c",
    "repeat/P02/list/screen.png": "f557edf6f691d10bd7918cd59e3adb9b5e67364d30e4d3513a642c6416690967",
    "repeat/P02/program.bin": "94004f0506878fb65d085704794e2b23ff94cb3373cb921ed638018ed3f84cd9",
    "repeat/P02/run/caprice.log": "7c3dff8f3cec4ee39c2de3ca15a15aa4025f7e0a4bd30c0160fbd0415c334713",
    "repeat/P02/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/P02/run/screen.png": "d7aef9e7a4a615abd1893706a7873f930a1b72ab9cca5b7c6d1809b75856ecfd",
    "repeat/P03/baseline/caprice.log": "bea4925a6c3ef5df5143a1f3f092ba537c943541d1c6fbe7cbaaf957448db794",
    "repeat/P03/baseline/screen.png": "5e8fdf75df94df52edb65169fb682bd96a4f73293e99945ddd7f5127f2ee806f",
    "repeat/P03/capture.json": "6a0c1a8e2c4e98d261f82d489500dc25ea1dc8b706b2276e2c73837eb0b203c4",
    "repeat/P03/list/caprice.log": "1eda4a3a071a66b4f391351d5160be69f443eb5b3ae11134ddee51a3f644d5aa",
    "repeat/P03/list/printer.dat": "b4cb51ca1a6b63fdc8e8d25ff45e07faaee295ffed24244338250b2d644845f5",
    "repeat/P03/list/screen.png": "fd7c2b2c85dcf4dfbf284a44996260b42db9a997330b22cc4ad1c40d3c49592b",
    "repeat/P03/program.bin": "b9e7018bf2a02514eb0573665c130d2740ad959324cc39714d064d00697882db",
    "repeat/P03/run/caprice.log": "69c5a460b58fb62c8877548f36fbdfc5ac6ee76592fdf9b9cc8d0b587d83d4d0",
    "repeat/P03/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/P03/run/screen.png": "0da462f8f24ddbadb7985036d33fbb6b979bbe596f8a3cef0daa6aeaa06c5f2f",
    "repeat/P04/baseline/caprice.log": "f93c364d508de361d100c50f500beb994e18464564b01628c48bfa3ebf16c132",
    "repeat/P04/baseline/screen.png": "6234af66576df2bc7e731bfc9950be0325ae2b2f51c9535d231a40b19ad645a6",
    "repeat/P04/capture.json": "4055ef0f6d4a1096024d6147fb8dab5bbf6c5c6e0bb3be9c34a30b0016ee194d",
    "repeat/P04/list/caprice.log": "e249dc94b5505126b3b97dde2a9136a6e3b36a035904f7ae0246743d2860ced9",
    "repeat/P04/list/printer.dat": "7b7a1af78c2bb89bc174012ecdc23e152583137b63161b8caa78a799c9d3bb28",
    "repeat/P04/list/screen.png": "730cb37db41758d81b9825f588be90e5d28d7e003ab41f24c40c4d4edc352279",
    "repeat/P04/program.bin": "ae65fefb678d48ec46c6ddf83d9867c8c3cbce2159527d3d0c1de64e7585a5cb",
    "repeat/P04/run/caprice.log": "31d722f09e19fec0812b944cb40bca0e2709143820114e5b7bb2631b123d6acf",
    "repeat/P04/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/P04/run/screen.png": "fced9757314fb9e8ddac1807f463306d1e9d5348643d4a66946fec098f77ca89",
    "repeat/P15/baseline/caprice.log": "f29bb0bce6d4b2dea540f6d1bdf3ad9eb97ebb8de87fad84e6965ecea54c988d",
    "repeat/P15/baseline/screen.png": "9c11004b03e4848687cabd983a41516ef7ea4c321c56f7a4d41db48beed352a9",
    "repeat/P15/capture.json": "3d09b356711cb4a4e3edcb79c97cf5487583e97c40bbb0177c2ebf942f91b5bc",
    "repeat/P15/list/caprice.log": "483ba21fac5eeddcbcae3bf7951e68a7711080a589f1b09d85bc002b20965099",
    "repeat/P15/list/printer.dat": "57cdc12820f7dd4969a930d407cc93e884923e7cd8d6c52d53b5654f94908544",
    "repeat/P15/list/screen.png": "646fad84c4d06e6947b92e2a240cac874d6317f4330f0c0de69c7e6ee962b98d",
    "repeat/P15/program.bin": "60923aed7048424af2b10b2a4fad12ece35dd1754b189a7391b815dc5bc5384d",
    "repeat/P15/run/caprice.log": "32ab6cd7542440b9c0f70bc94642b1135358bb608126ab5b1bb072d3c7d8e78b",
    "repeat/P15/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/P15/run/screen.png": "afa0a87092587cd7259b86a3d47f8acd82f2d48b177ad76c231940f002e8c0d1",
    "repeat/P16/baseline/caprice.log": "3a431db37afe8f40c70e66a8218dcf39db39236906026236165ea7df3451e022",
    "repeat/P16/baseline/screen.png": "5e8fdf75df94df52edb65169fb682bd96a4f73293e99945ddd7f5127f2ee806f",
    "repeat/P16/capture.json": "247b1078c0ae1f2a95f2e7f70242880d15690fc2c4d331e78e26c50576d20115",
    "repeat/P16/list/caprice.log": "6608908f64b10cdbd07df6e15727d307e018f9ff17cd2e1662b37a5113de17d7",
    "repeat/P16/list/printer.dat": "2e487baa1f6eb1693f51c0b6e3a1eb3fb8d15d22e168d0f01a44d2233b61a3bf",
    "repeat/P16/list/screen.png": "8c9a642c2b2f7a540ab716df52deffa82d55d3f64fa0b8bca2464a4b0dda759e",
    "repeat/P16/program.bin": "c997bdf177482cc4d9707ed63a5f3eb9db28edc58aa568d7940d99c6c083d9ed",
    "repeat/P16/run/caprice.log": "b5dc7ea43431fe28ceac16233a5fc0973e28fec96a5b253b0dde353dba584aa1",
    "repeat/P16/run/printer.dat": "d339b4cf87335e2e86603aae9b87935df5a97dd981f0edd464b214b3c4cb15db",
    "repeat/P16/run/screen.png": "7b3d830699116d7d282fa436540f5d9cacb42c14301c4f699ae41100a0883e4e",
    "repeat/PN1/baseline/caprice.log": "79446dd0175d949436cee0ff304be487d78a0308f4cac8723d5785976ad05a7c",
    "repeat/PN1/baseline/screen.png": "9c11004b03e4848687cabd983a41516ef7ea4c321c56f7a4d41db48beed352a9",
    "repeat/PN1/capture.json": "8d9453d5e5194bfaa6c861291b2d1f274f5ed457387d811eafb9334569535f88",
    "repeat/PN1/list/caprice.log": "aad12ad07db38bcd9520aba64435a17e38faec8f8d468a8e81962e12e2f6acf3",
    "repeat/PN1/list/printer.dat": "b6cb9fad5366a6caa7310e533b795ce68add3daae7665d4ad7b92ebc238788e8",
    "repeat/PN1/list/screen.png": "5c5a6ea962e1206cdccf639ea9c355fa3985f7ce20261d6e9e19e50839c89278",
    "repeat/PN1/program.bin": "db6d2173311f67ef4c36a6e2e4a82cddb94930cdfbf5705edb96edcd400a4825",
    "repeat/PN1/run/caprice.log": "2b785e35efb094c84a20f7a460fba9e632f933a4b57d29356a150c1ea646eb88",
    "repeat/PN1/run/printer.dat": "d339b4cf87335e2e86603aae9b87935df5a97dd981f0edd464b214b3c4cb15db",
    "repeat/PN1/run/screen.png": "b33d2a7f6096928f1c44a208db55df0fc9dfa0ee8e4e740d7bbe63462239a443",
    "repeat/SCHANGE/baseline/caprice.log": "dc41e41b7369ac9639f06aafe5baf42cb0ccf0bb87f5af8021f9c601362c8f80",
    "repeat/SCHANGE/baseline/screen.png": "9c11004b03e4848687cabd983a41516ef7ea4c321c56f7a4d41db48beed352a9",
    "repeat/SCHANGE/capture.json": "de151ec4677d3431e4bad7c9ce1a4d1e70a262795a879903c444dcbdafb9e63e",
    "repeat/SCHANGE/list/caprice.log": "e71580ff82edf3844d8961662a3e34742d6b093e14417c4a22a1972f3d3f3bb4",
    "repeat/SCHANGE/list/printer.dat": "ce5bda694db29128de8475c9d11efe609ad2bc0fab11375afc0635f0de8fc15b",
    "repeat/SCHANGE/list/screen.png": "7897ee7c63ad671d3e2104cb3cb9033987791001b070e486604cfd48891e21bc",
    "repeat/SCHANGE/program.bin": "2221c9775f56e62485e215fe9e75378c8db380591db6448dd97175fb7b603078",
    "repeat/SCHANGE/run/caprice.log": "157135f8ccf54cd2b97ed0b3e9377e34af96030bc81d9c9f574fe3fa8d8b81db",
    "repeat/SCHANGE/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/SCHANGE/run/screen.png": "3cb7867a4b057daa4937b46d2fae832e0f75d1d5326c3394404f72c977a705a4",
    "repeat/SCLS/baseline/caprice.log": "db57b3fda6bc4ddcde75f63cf9eb59394758051a52fc65ac8d5272236acecd6e",
    "repeat/SCLS/baseline/screen.png": "f5f21a05e20747c34eb264d1462b53618598247fa868725b5f352e1ff84ea019",
    "repeat/SCLS/capture.json": "ee1646c6225b329da96f5af7210e40d45debf1bc7233a43c00dee6da5397af49",
    "repeat/SCLS/list/caprice.log": "24f18312de0e24770c089411f7141e877e6627999c3d23a08d9e5709b556743f",
    "repeat/SCLS/list/printer.dat": "dc247e51dbfc1aa1e1fa2d36448044abe62e3d83e82a741d3c7375f1a533e4fd",
    "repeat/SCLS/list/screen.png": "f667a49961583732a6404aecb4e5e52a2917e8670806ec00a465cfd061d65b78",
    "repeat/SCLS/program.bin": "336394c3f9e0cc54767ff51443d00752d6447ff3dd82eabdc3be9517839eedf9",
    "repeat/SCLS/run/caprice.log": "8023cc2fe2051739814c3b47a0ae29b54ae11b73f2a6ad2b15095e3436161bf6",
    "repeat/SCLS/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/SCLS/run/screen.png": "40817b6b25891d0d74cc25e48bb953060f5e7edfd08c81ab39a73b220cc42769",
    "repeat/SINK/baseline/caprice.log": "b3d7a9ec3d8a7554d625ec4dcd1d18951a61af36af885e9057967b1837502d90",
    "repeat/SINK/baseline/screen.png": "f5f21a05e20747c34eb264d1462b53618598247fa868725b5f352e1ff84ea019",
    "repeat/SINK/capture.json": "07332779049c3e16af98301f7dade070279768b0f51323fb9c5713dd7db6766a",
    "repeat/SINK/list/caprice.log": "1b1acbb78d25bd3a670f112f0bca8d66e3d84e38295fcd80535e6cd10da4f43f",
    "repeat/SINK/list/printer.dat": "f714eb314991c526a537253f117feb8fec72b4aad7d63adc8100e91cb192b7f7",
    "repeat/SINK/list/screen.png": "46bd2496d035575212ed767c00f62f55a65dad24747db58aa7f53ff5d3c56fe7",
    "repeat/SINK/program.bin": "7b4e1b07d46b625099a3ed14d8fa8ee9295e57427fabee324a3436aadea0fdb4",
    "repeat/SINK/run/caprice.log": "808de39753def96e120a5e8ecd1b913113d16bb0ca245e272d37a70cc9d9ef26",
    "repeat/SINK/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/SINK/run/screen.png": "d44d131189289b2a6c0536badb6d9dc31f6c390ff14f36d62773549cc3eef86e",
    "repeat/SPRINT/baseline/caprice.log": "c8702eb21a172b9395961268b35500db1470f043153af6860ffd3507d89b05c7",
    "repeat/SPRINT/baseline/screen.png": "db8af206aa1bd782870c96836a7a2acd031d0fbb872adcfe68429ed3072f9ee1",
    "repeat/SPRINT/capture.json": "e44c97cd50499624abfa473c4788da7b00262b8620aaa7113381a8a8d8a6966d",
    "repeat/SPRINT/list/caprice.log": "f145c7f7196debb2fc02f8e97d488f1670089cdd2bc4cdca85156f840fc9a83a",
    "repeat/SPRINT/list/printer.dat": "a7fd9cbfc4c4300c54ecffda8949e051bc32bce438a8cb4b6d8c3907ddddf282",
    "repeat/SPRINT/list/screen.png": "42eefce529100b69aff004e9ee964ab0713e81f7bc14d0e45bb9f8ec927e27f8",
    "repeat/SPRINT/program.bin": "758641f723ed91ca4e87e42bb57dfa3efc2b7d891f2df40886ac8ee5aff9895b",
    "repeat/SPRINT/run/caprice.log": "d6cd1e7a1f5b0395a8e5f0be0e4194a61d5f0a15d9e4183cea14b9ab21c8f406",
    "repeat/SPRINT/run/printer.dat": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "repeat/SPRINT/run/screen.png": "52091a9e5697dfad8c6c44f541d97762a19b76d7322c6250161b76bd151a4b50",
    "repeat/chronology/caprice.log": "06dc582ab3f189971cf4a42bd19bcd2f83a642df264efb2c579a33cd1584758a",
    "repeat/chronology/capture.json": "330a87a1c021a6b56925dee9178609fc4bdfd9d438bc5663567123dcca46b7de",
    "repeat/chronology/screen_0.png": "71464943f8a0843b0a324811847b8f8ccb8050f2547f542103dc9b2bab8adb2d",
    "repeat/chronology/screen_1.png": "6cbc0db799d006061e62df80157c62161b2b08e0f8459e7b6f7f40b13f5ce298",
    "repeat/direct/D16/caprice.log": "ee56532191a501e342ce2307ae8771c0eded5ddbdfd6e2aabfc21fb91aeafcb2",
    "repeat/direct/D16/capture.json": "700802480c7d87bacbd574c05a2783554ef8bde231cb87dbe3bfefdab80fdebb",
    "repeat/direct/D16/printer.dat": "16369e608df84ec5e441306ef7e915d640ad81bd0796bf3ec2e0c901b190b37b",
    "repeat/direct/D16/screen.png": "d690dc58c71b2fbdbbb715aad45ecff0da2277cc228b3a28010eb1c2f090aa3b",
    "repeat/direct/DN1/caprice.log": "e7605c6218c5b42616020338d8678cc488a4df2a9924d3d5e7e42f4bc916e338",
    "repeat/direct/DN1/capture.json": "cf19bfd718064d864c7726ccbf52a395d6ee9a30cfee50deeb325c3cc99cdb66",
    "repeat/direct/DN1/printer.dat": "16369e608df84ec5e441306ef7e915d640ad81bd0796bf3ec2e0c901b190b37b",
    "repeat/direct/DN1/screen.png": "5b2cadf7a94cdd851f68c5b566fc39f135ba3c14fa4ba6abf711427d5a2d7310"
}
PRINT_LABEL = 'J119TEST'
SETUP = ('MODE 1', 'INK 0,0', 'INK 1,26', 'INK 2,6', 'INK 3,18',
         'PAPER 0', 'PEN 1', 'CLS', 'NEW')
PNG_PATHS = ('list/screen.png', 'baseline/screen.png', 'run/screen.png')
CASE_FILES = ('program.bin', 'capture.json', 'list/screen.png', 'list/caprice.log',
              'list/printer.dat', 'baseline/screen.png', 'baseline/caprice.log',
              'run/screen.png', 'run/caprice.log', 'run/printer.dat')
CHRON_FILES = ('capture.json', 'caprice.log', 'screen_0.png', 'screen_1.png')
DIRECT_CASES = {'D16':'PAPER 16', 'DN1':'PAPER -1'}
DIRECT_FILES = ('capture.json', 'caprice.log', 'screen.png', 'printer.dat')
ROI = (64, 305, 190, 321)  # prior INK oracle glyph location; still empirical here
ROI_SECOND_ROW = (64, 321, 190, 337)  # separate evidence for text printed after PAPER change
ROI_BLANK = (210, 180, 260, 200)  # screen area away from controlled glyph (CLS/background)


class Invalid(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise Invalid(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode('ascii')


def source(case):
    return (SOURCES / (case + '.bas')).read_bytes()


def expected_source(case):
    if case in BASIC:
        lines = (f'10 REM J119-{case}', f'20 PAPER {BASIC[case]}',
                 '30 LOCATE 1,15', f'40 PRINT "{PRINT_LABEL}"', '50 END')
    else:
        lines = SCENARIOS[case]
    return ('\n'.join(lines) + '\n').encode('ascii')


def check_sources():
    need(set(p.name for p in SOURCES.glob('*.bas')) == {x + '.bas' for x in CASES},
         'SOURCE_INVENTORY')
    for case in CASES:
        need(source(case) == expected_source(case), 'SOURCE_CHANGED_' + case)
    return True


def require_git_head(head):
    need(re.fullmatch(r'[0-9a-f]{40}', head) is not None, 'HEAD_SYNTAX')
    actual = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    need(actual == head, 'FALSE_HEAD')
    return head


def is_ancestor(head):
    return subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor',
                           head, 'HEAD'], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def prior_tools():
    """Only acquisition/verification imports prior unmodified, pinned CPC readers."""
    sys.path.insert(0, str(ROOT / 'tools'))
    import j1_18_a_ink_evidence as ink  # original ROM acquisition primitives
    import j1_18_a_ink_pixels as pixels  # independently CRC-checked PNG decoder
    return ink, pixels


def file_map():
    paths = {}
    for session in SESSIONS:
        for case in CASES:
            for name in CASE_FILES:
                rel = f'{session}/{case}/{name}'
                paths[rel] = None
        for name in CHRON_FILES:
            paths[f'{session}/chronology/{name}'] = None
        for case in DIRECT_CASES:
            for name in DIRECT_FILES:
                paths[f'{session}/direct/{case}/{name}'] = None
    return paths


def histogram(rows, roi):
    x0,y0,x1,y1 = roi
    need(len(rows) >= y1 and 0 <= x0 < x1 <= 768 and 0 <= y0 < y1 <= 540, 'ROI_RANGE')
    colors = {}
    for y in range(y0, y1):
        for x in range(x0, x1):
            rgb = ','.join(str(v) for v in rows[y][x*3:x*3+3])
            colors[rgb] = colors.get(rgb, 0) + 1
    need(sum(colors.values()) == (x1-x0)*(y1-y0), 'ROI_COUNT')
    return colors


def capture_case(cap, out, session, case, tmp, ink, pixels):
    work = out/session/case
    raw_lines = source(case).decode('ascii').splitlines()
    _, _, _, _ = session, case, ink, pixels
    lsnap = tmp / (session + '-' + case)
    lsnap.mkdir()
    # Pre-RUN genuine ROM LIST screenshot + snapshot + independent printer LIST.
    cl = list(SETUP) + raw_lines + ['LIST',
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT',
        'LIST #8', 'CAP32_DELAY CAP32_EXIT']
    lt = ink.launch(cap, work/'list', lsnap, cl, True)
    snaps = list(lsnap.glob('*.sna'))
    need(len(snaps) == 1, 'PRE_RUN_SNA_' + case)
    prog,region = ink.cpc.extract_snapshot(snaps[0].read_bytes(),
                  [int(x.split(' ',1)[0]) for x in raw_lines])
    nums, records = ink.cpc.records(prog)
    need(len(records) == len(raw_lines), 'RAM_RECORD_COUNT_' + case)
    (work/'program.bin').write_bytes(prog)
    list_raw = (work/'list/printer.dat').read_bytes()
    need(bool(list_raw), 'LIST_PRINTER_EMPTY_' + case)
    # Baseline text control in a new emulator process; no PAPER case executed.
    baseline = list(SETUP) + ['LOCATE 1,15', f'PRINT "{PRINT_LABEL}"',
                              'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT']
    bt = ink.launch(cap, work/'baseline', tmp, baseline, False)
    # RUN error screenshot is captured *before* ERR/ERL printer reads.
    cr = list(SETUP) + raw_lines + ['RUN',
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
        'PRINT #8,ERR', 'PRINT #8,ERL', 'CAP32_DELAY CAP32_EXIT']
    rt = ink.launch(cap, work/'run', tmp, cr, True)
    printer = (work/'run/printer.dat').read_bytes()
    parsed = [ink.parse_integer(v) for v in printer.splitlines(keepends=True)]
    need(len(parsed) == 2 and all(v is not None for v in parsed), 'ERR_ERL_CAPTURE_' + case)
    err,erl = (v['numeric_value'] for v in parsed)
    # Runtime observed statuses only. No textual error is inferred from ERR/ERL.
    visual = {}
    for name in PNG_PATHS:
        rows = pixels.png_rgb(work/name)
        visual[name] = {'sha256': digest((work/name).read_bytes()),
                        'roi': list(ROI), 'rgb_histogram': histogram(rows, ROI),
                        'blank_roi':list(ROI_BLANK),'blank_rgb_histogram':histogram(rows,ROI_BLANK)}
    row_hex = {str(n): prog[r['offset']:r['offset']+r['length']].hex(' ').upper()
               for n,r in zip(nums,records)}
    d = {'case':case,'session':session,'phase':PHASE,'source_sha256':digest(source(case)),
         'program_sha256':digest(prog),'program_hex':prog.hex(' ').upper(),
         'lines':nums,'ram_lines_hex':row_hex,'region':region,
         'setup':list(SETUP),'commands':{'list':cl,'baseline':baseline,'run':cr},
         'metadata':{'list':lt,'baseline':bt,'run':rt},
         'err':err,'erl':erl,'printer_hex':printer.hex(),
         'list_printer_hex':list_raw.hex(),
         'diagnostic_text':'DIAG_CPC_UNVERIFIED',
         'visual':visual,'visual_classification':'VISUAL_UNVERIFIED',
         'source_kind':'CPC6128_CAPRICE32_REAL_ACQUISITION'}
    (work/'capture.json').write_bytes(canonical(d))
    return d


def capture_chronology(cap, out, session, tmp, ink, pixels):
    """Extra in-process two-frame chronology, 2 fresh sessions, not a substitute for 12 cases."""
    dest = out/session/'chronology'
    cmds = list(SETUP) + ['LOCATE 1,15','PRINT "J119OLD"',
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
        'PAPER 2', 'LOCATE 1,16','PRINT "J119NEW"',
        ink.CHRONO_DELAY + ' CAP32_SCRNSHOT CAP32_EXIT']
    meta = ink.launch(cap,dest,tmp,cmds,False,shots=2)
    observations = {}
    for n in (0,1):
        img = dest/f'screen_{n}.png'
        observations[str(n)] = {'sha256':digest(img.read_bytes()),
                                  'roi':list(ROI),
                                  'rgb_histogram':histogram(pixels.png_rgb(img),ROI),
                                  'second_roi':list(ROI_SECOND_ROW),
                                  'second_rgb_histogram':histogram(pixels.png_rgb(img),ROI_SECOND_ROW)}
    (dest/'capture.json').write_bytes(canonical({'session':session,'commands':cmds,
        'phase':PHASE,'caprice':meta,'visual':observations,
        'visual_classification':'VISUAL_UNVERIFIED',
        'intervening_print':True,'source_kind':'CPC6128_CAPRICE32_REAL_ACQUISITION'}))



def capture_direct(cap, out, session, case, tmp, ink, pixels):
    """Supplementary direct-mode candidate, not a numbered-program oracle."""
    dest = out/session/'direct'/case
    cmds = list(SETUP) + [DIRECT_CASES[case],
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
        'PRINT #8,ERR', 'PRINT #8,ERL', 'CAP32_DELAY CAP32_EXIT']
    metadata = ink.launch(cap,dest,tmp,cmds,True)
    raw = (dest/'printer.dat').read_bytes()
    values = [ink.parse_integer(x) for x in raw.splitlines(keepends=True)]
    need(len(values)==2 and all(x is not None for x in values), 'DIRECT_ERR_ERL_'+case)
    img=dest/'screen.png'
    (dest/'capture.json').write_bytes(canonical({
        'session':session,'case':case,'phase':PHASE,'statement':DIRECT_CASES[case],
        'commands':cmds,'caprice':metadata,'source_kind':'CPC6128_CAPRICE32_REAL_ACQUISITION',
        'err':values[0]['numeric_value'],'erl':values[1]['numeric_value'],
        'printer_hex':raw.hex(),'diagnostic_text':'DIAG_CPC_UNVERIFIED',
        'visual':{'sha256':digest(img.read_bytes()),'roi':list(ROI),
                  'rgb_histogram':histogram(pixels.png_rgb(img),ROI),
                                  'second_roi':list(ROI_SECOND_ROW),
                                  'second_rgb_histogram':histogram(pixels.png_rgb(img),ROI_SECOND_ROW)}}))


def acquire(cap, output, head):
    need(not output.exists(), 'OUTPUT_ALREADY_EXISTS')
    require_git_head(head)
    check_sources()
    ink,pixels = prior_tools()
    version = ink.check_caprice(cap)
    need(ink.cpc.ROM_SHA == ROM_SHA256 and ink.cpc.PIN == CAPRICE_COMMIT,
         'ORACLE_ROM_OR_CAPRICE_DRIFT')
    # Temporary inputs never archived: only program.bin from real CPC SNA.
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='j119-paper-sna-') as tmp:
        for session in SESSIONS:
            for case in CASES:
                d=capture_case(cap,output,session,case,Path(tmp),ink,pixels)
                print(PHASE,case,session,'RAM',d['ram_lines_hex'],'ERR',d['err'],
                      'ERL',d['erl'],flush=True)
            capture_chronology(cap,output,session,Path(tmp),ink,pixels)
            for case in DIRECT_CASES:
                capture_direct(cap,output,session,case,Path(tmp),ink,pixels)
    hashes = {name:digest((output/name).read_bytes()) for name in file_map()}
    m = {'schema_version':1,'phase':PHASE,'acquisition_head':head,
         'origin':'CAPRICE32_REAL_ONLY',
         'run_id':os.environ.get('GITHUB_RUN_ID','LOCAL'),
         'oracle':{'rom_sha256':ROM_SHA256,'caprice_commit':CAPRICE_COMMIT,
                   'ghcr':GHCR,'model':'CPC6128','basic':'1.1','version':version},
         'cases':list(CASES),'sessions':list(SESSIONS),'files':hashes,
         'diagnostic_text':'DIAG_CPC_UNVERIFIED',
         'visual_classification':'VISUAL_UNVERIFIED',
         'full_snapshots_archived':False,'native_changes':False}
    (output/'manifest.json').write_bytes(canonical(m))
    verify(output, permanent=False)
    print(PHASE,'FRESH_ACQUISITION_UNSEALED',len(CASES)*2, 'sessions',flush=True)


def verify(root, permanent=False):
    need((root/'manifest.json').is_file(), 'ARCHIVE_ABSENT')
    m = json.loads((root/'manifest.json').read_bytes())
    need(m.get('schema_version') == 1 and m.get('phase') == PHASE and
         m.get('origin') == 'CAPRICE32_REAL_ONLY' and
         m.get('cases') == list(CASES) and m.get('sessions') == list(SESSIONS) and
         m.get('full_snapshots_archived') is False and m.get('native_changes') is False and
         m.get('oracle',{}).get('rom_sha256') == ROM_SHA256 and
         m.get('oracle',{}).get('caprice_commit') == CAPRICE_COMMIT and
         m.get('oracle',{}).get('ghcr') == GHCR, 'MANIFEST_PROVENANCE')
    head=m.get('acquisition_head','')
    need(re.fullmatch(r'[0-9a-f]{40}',head) is not None and is_ancestor(head),
         'FALSE_HEAD_OR_ANCESTRY')
    expected=set(file_map())
    seen={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    need(seen == expected | {'manifest.json'}, 'FILE_INVENTORY')
    need(set(m.get('files',{})) == expected, 'MANIFEST_FILES')
    if permanent:
        need(bool(re.fullmatch(r'[a-f0-9]{64}',SEALED_MANIFEST_SHA256 or '')) and
             bool(re.fullmatch(r'[a-f0-9]{40}',SEALED_ACQUISITION_PARENT or '')) and
             bool(SEALED_FILE_SHA256) and set(SEALED_FILE_SHA256) == expected,
             'EXTERNAL_SEAL_NOT_ACQUIRED')
        need(head == SEALED_ACQUISITION_PARENT and
             digest((root/'manifest.json').read_bytes()) == SEALED_MANIFEST_SHA256,
             'FALSE_SEALED_HEAD_OR_MANIFEST')
    for name in sorted(expected):
        raw=(root/name).read_bytes()
        need(digest(raw) == m['files'][name], 'SHA_'+name)
        if permanent:
            need(digest(raw)==SEALED_FILE_SHA256[name], 'EXTERNAL_SHA_'+name)
    ink,pixels=prior_tools()
    records={}
    directs={}
    chronologies={}
    for session in SESSIONS:
        for case in CASES:
            base=root/session/case
            d=json.loads((base/'capture.json').read_bytes())
            need(d.get('case')==case and d.get('session')==session and
                 d.get('phase')==PHASE and d.get('setup')==list(SETUP) and
                 d.get('source_kind')=='CPC6128_CAPRICE32_REAL_ACQUISITION' and
                 d.get('source_sha256')==digest(source(case)) and
                 d.get('commands',{}).get('list') == list(SETUP)+source(case).decode('ascii').splitlines()+['LIST', 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT', 'LIST #8','CAP32_DELAY CAP32_EXIT'] and
                 d.get('commands',{}).get('run') == list(SETUP)+source(case).decode('ascii').splitlines()+['RUN','CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT','PRINT #8,ERR','PRINT #8,ERL','CAP32_DELAY CAP32_EXIT'] and
                 d.get('diagnostic_text')=='DIAG_CPC_UNVERIFIED',
                 'CAPTURE_PROVENANCE_'+case+session)
            raw=(base/'program.bin').read_bytes()
            nums,rows=ink.cpc.records(raw)
            need(d.get('program_sha256')==digest(raw) and
                 d.get('program_hex')==raw.hex(' ').upper() and
                 d.get('lines')==nums and
                 d.get('ram_lines_hex') == {str(n):raw[r['offset']:r['offset']+r['length']].hex(' ').upper()
                              for n,r in zip(nums,rows)} and
                 nums==[int(line.split(' ',1)[0]) for line in source(case).decode().splitlines()],
                 'RAM_OR_LIST_'+case+session)
            for png_name in PNG_PATHS:
                png=base/png_name
                pic=pixels.png_rgb(png)
                need(d['visual'][png_name]['sha256']==digest(png.read_bytes()) and
                     d['visual'][png_name]['rgb_histogram']==histogram(pic,ROI) and
                     d['visual'][png_name]['blank_rgb_histogram']==histogram(pic,ROI_BLANK),
                     'PNG_CRC_OR_ROI_'+case+session+png_name)
            expect_printer=(base/'run/printer.dat').read_bytes()
            parsed=[ink.parse_integer(v) for v in expect_printer.splitlines(keepends=True)]
            need(len(parsed)==2 and all(v is not None for v in parsed) and
                 d.get('printer_hex')==expect_printer.hex() and
                 (d['err'],d['erl']) == tuple(v['numeric_value'] for v in parsed) and
                 d.get('list_printer_hex')==(base/'list/printer.dat').read_bytes().hex(),
                 'ERR_ERL_OR_LIST_'+case+session)
            records[(case,session)]=d
        for case in DIRECT_CASES:
            direct=root/session/'direct'/case
            d=json.loads((direct/'capture.json').read_bytes())
            raw=(direct/'printer.dat').read_bytes()
            parsed=[ink.parse_integer(x) for x in raw.splitlines(keepends=True)]
            need(len(parsed)==2 and all(x is not None for x in parsed) and
                 d.get('session')==session and d.get('statement')==DIRECT_CASES[case] and
                 d.get('commands')==list(SETUP)+[DIRECT_CASES[case],
                 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                 'PRINT #8,ERR','PRINT #8,ERL','CAP32_DELAY CAP32_EXIT'] and
                 d.get('source_kind')=='CPC6128_CAPRICE32_REAL_ACQUISITION' and
                 d.get('printer_hex')==raw.hex() and
                 (d.get('err'),d.get('erl'))==tuple(x['numeric_value'] for x in parsed) and
                 d.get('diagnostic_text')=='DIAG_CPC_UNVERIFIED', 'DIRECT_PROVENANCE_'+case)
            directs[(case,session)]=d
            png=direct/'screen.png'
            need(d['visual']['sha256']==digest(png.read_bytes()) and
                 d['visual']['rgb_histogram']==histogram(pixels.png_rgb(png),ROI),
                 'DIRECT_PNG_CRC_OR_ROI_'+case)
        chronology=root/session/'chronology'
        ch=json.loads((chronology/'capture.json').read_bytes())
        chronologies[session]=ch
        need(ch.get('phase')==PHASE and ch.get('session')==session and
             ch.get('source_kind')=='CPC6128_CAPRICE32_REAL_ACQUISITION' and
             ch.get('intervening_print') is True, 'CHRONO_PROVENANCE')
        for n in (0,1):
            p=chronology/f'screen_{n}.png'
            need(ch['visual'][str(n)]['sha256']==digest(p.read_bytes()) and
                 ch['visual'][str(n)]['rgb_histogram']==histogram(pixels.png_rgb(p),ROI) and
                 ch['visual'][str(n)]['second_rgb_histogram']==histogram(pixels.png_rgb(p),ROI_SECOND_ROW),
                 'CHRONO_PNG_CRC_OR_ROI')
    for case in CASES:
        a,b=(records[(case,s)] for s in SESSIONS)
        need(a['program_hex']==b['program_hex'] and
             (a['err'],a['erl'])==(b['err'],b['erl']) and
             a['list_printer_hex']==b['list_printer_hex'] and
             a['metadata']['list']['started_utc'] != b['metadata']['list']['started_utc'] and
             a['metadata']['run']['started_utc'] != b['metadata']['run']['started_utc'],
             'INDEPENDENT_MISMATCH_'+case)
        for name in ('run/screen.png','baseline/screen.png'):
            need(a['visual'][name]['rgb_histogram'] == b['visual'][name]['rgb_histogram'] and
                 a['visual'][name]['blank_rgb_histogram'] == b['visual'][name]['blank_rgb_histogram'],
                 'INDEPENDENT_RGB_MISMATCH_'+case+name)
    for case in DIRECT_CASES:
        a,b=(directs[(case,s)] for s in SESSIONS)
        need((a['err'],a['erl'])==(b['err'],b['erl']) and
             a['visual']['rgb_histogram']==b['visual']['rgb_histogram'],
             'INDEPENDENT_DIRECT_MISMATCH_'+case)
    for n in ('0','1'):
        need(chronologies['original']['visual'][n]['rgb_histogram'] ==
             chronologies['repeat']['visual'][n]['rgb_histogram'] and
             chronologies['original']['visual'][n]['second_rgb_histogram'] ==
             chronologies['repeat']['visual'][n]['second_rgb_histogram'],
             'INDEPENDENT_CHRONO_RGB_MISMATCH_'+n)
    return {'source':'CPC6128_CAPRICE32_REAL_ONLY','cases':len(CASES),
            'sessions':len(CASES)*2,'seal':'EXTERNAL_SEALED' if permanent else 'UNSEALED'}


def self_test():
    """Negative controls are deliberately synthetic and NEVER an oracle PASS."""
    import unittest
    class ContractTests(unittest.TestCase):
        def test_inventory(self):
            self.assertEqual(len(CASES),12)
            self.assertEqual(len(file_map()),12*2*len(CASE_FILES)+2*len(CHRON_FILES)+2*len(DIRECT_CASES)*len(DIRECT_FILES))
            self.assertTrue(check_sources())
        def test_no_archive(self):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(Invalid,'ARCHIVE_ABSENT'):
                    verify(Path(tmp),permanent=True)
        def test_no_auto_seal(self):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'manifest.json';p.write_text('{}')
                with self.assertRaisesRegex(Invalid,'MANIFEST_PROVENANCE'):
                    verify(Path(tmp),permanent=True)
        def test_false_head(self):
            with self.assertRaisesRegex(Invalid,'HEAD_SYNTAX'):
                require_git_head('abcdef')
        def test_corrupt_source(self):
            self.assertEqual(expected_source('P16').splitlines()[1],b'20 PAPER 16')
            self.assertEqual(expected_source('PN1').splitlines()[1],b'20 PAPER -1')
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests)
    results=unittest.TextTestRunner(verbosity=1).run(suite)
    need(results.wasSuccessful(), 'OFFLINE_SELF_TEST_FAILURE')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-sources', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--acquire',type=Path, help='pinned Caprice32 directory (contains cap32, cfg, ROM)')
    parser.add_argument('--output',type=Path,help='new archive destination, must not exist')
    parser.add_argument('--head', help='full exact checkout commit SHA')
    parser.add_argument('--evidence',type=Path)
    parser.add_argument('--permanent',action='store_true')
    args=parser.parse_args()
    need(any((args.check_sources,args.self_test,args.acquire,args.evidence)), 'NO_OPERATION')
    if args.check_sources or args.self_test or args.acquire:
        check_sources()
    if args.self_test:
        self_test()
    if args.acquire:
        need(args.output is not None and args.head is not None and not args.evidence, 'ACQUIRE_ARGS')
        acquire(args.acquire.resolve(),args.output.resolve(),args.head)
    if args.evidence:
        result=verify(args.evidence.resolve(),args.permanent)
        print('J1.19-A ARCHIVE_VERIFIED',result)
    else:
        need(not args.permanent,'PERMANENT_WITHOUT_ARCHIVE')

if __name__=='__main__':
    try:
        main()
    except (Invalid,OSError,ValueError,KeyError,IndexError,subprocess.SubprocessError,
            UnicodeError,json.JSONDecodeError,ImportError) as error:
        print('J1.19-A FAIL',error,file=sys.stderr)
        sys.exit(1)
