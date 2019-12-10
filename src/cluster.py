#!/usr/bin/env python3

import os
import sys
import getopt
import shutil

#jenkins library configuration
sys.path.append(os.path.abspath(os.environ['WORKSPACE'] + "/src/tests"))
sys.path.append(os.path.abspath(os.environ['WORKSPACE'] + "/src/tests/lib"))

from tests.lib.aux import *
from tests.lib.terraform import *

mode = ""
configs = ""
testsRoot = "tests/"
publicRepo = "https://ocre-testsuite.rtfd.io"

# -----------------CMD OPTIONS--------------------------------------------
try:
    options, remainder = getopt.getopt(sys.argv[1:],
                "cd", ["create=", "destroy"])
except getopt.GetoptError as err:
    print(err)
    stop(1)

for opt, arg in options:
    if opt in ('-c', '--create'):
        mode = "create"
        configs = arg
        print("Using config path: " + arg)
    elif opt in ('-d', '--destroy'):
        mode = "destroy"

# ----------------RUN TESTS-----------------------------------------------
if mode == "create":
    logger(
        "Creating cluster ...",
        "=",
        False)
    configs = loadFile(configs, required=True)
    instanceDefinition = loadFile("../configurations/instanceDefinition")
    extraInstanceConfig = loadFile("../configurations/extraInstanceConfig")
    dependencies = loadFile("../configurations/dependencies")
    credentials = loadFile("../configurations/credentials")
    provDict = loadFile("schemas/provDict.yaml",
                    required=True)["allProviders"]
    extraSupportedClouds = loadFile("schemas/provDict.yaml",
                                required=True)["extraSupportedClouds"]
    baseCWD = os.getcwd()

    prov, msg = terraformProvisionment("shared",
                                           1,
                                           None,
                                           None,
                                           "logging/shared",
                                           configs,
                                           testsRoot,
                                           True,
                                           instanceDefinition,
                                           credentials,
                                           dependencies,
                                           baseCWD,
                                           provDict,
                                           extraSupportedClouds)
    if prov is False:
        print(msg)
    stop(0)

elif mode == "destroy":
    logger(
        "Destroying cluster ...",
        "=",
         False)
    destroyTF("tests/")
    stop(0)
