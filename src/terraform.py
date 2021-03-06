#!/usr/bin/env python3

import os
import time
import random
import string

from aux import *

provisionFailMsg = "Failed to provision raw VMs. Check 'logs' file for details"
bootstrapFailMsg = "Failed to bootstrap '%s' k8s cluster. Check 'logs' file"


def runTerraform(mainTfDir, baseCWD, test, msg, autoApprove=True):
    """Run Terraform cmds.

    Parameters:
        mainTfDir (str): Path where the .tf file is.
        baseCWD (str): Path to go back.
        test (str): Cluster identification.
        msg (str): Message to be shown.
        autoApprove (bool): If True (default) use '-auto-approve' option

    Returns:
        int: 0 for success, 1 for failure
    """

    toLog = "logging/%s" % test
    writeToFile(toLog, msg, True)
    os.chdir(mainTfDir)
    beautify = "terraform fmt > /dev/null &&"
    tfCMD = "terraform init && %s terraform apply -auto-approve" % beautify
    if autoApprove is False:
        tfCMD = "terraform init && %s terraform apply" % beautify

    tfScript = """
    ((%s) && touch /tmp/validTFrun) |

    while read line; do echo [ %s ] $line; done

    if [ -f /tmp/validTFrun ]; then
    	rm -f /tmp/validTFrun
    	exit 0
    fi
    exit 1
    """ % (tfCMD, test)

    exitCode = runCMD(tfScript)
    os.chdir(baseCWD)
    return exitCode


def cleanupTF(mainTfDir):
    """Delete existing terraform stuff in the specified folder.

    Parameters:
        mainTfDir (str): Path to the .tf file.
    """

    for filename in [
        "join.sh",
        "main.tf",
        "terraform.tfstate",
        "terraform.tfstate.backup",
            ".terraform"]:
        file = "%s/%s" % (mainTfDir, filename)
        if os.path.isfile(file):
            os.remove(file)
        if os.path.isdir(file):
            shutil.rmtree(file, True)


def stackVersioning(variables, configs):
    """Adds stack versioning related stuff to the variables section of the
       .tf file.

    Parameters:
        variables (str): Variables section of the .tf file.
        configs (dict): Object containing configs.yaml's configurations.

    Returns:
        string: modified variables section, stack versioning stuff added.
    """

    variables = variables.replace("DOCKER_CE_PH", tryTakeFromYaml(configs, "dockerCE", ""))
    variables = variables.replace("DOCKER_EN_PH", tryTakeFromYaml(configs, "dockerEngine", ""))
    variables = variables.replace("K8S_PH", tryTakeFromYaml(configs, "kubernetes", ""))

    return variables


def terraformProvisionment(
        test,
        nodes,
        flavor,
        extraInstanceConfig,
        toLog,
        configs,
        testsRoot,
        retry,
        instanceDefinition,
        credentials,
        dependencies,
        baseCWD,
        provDict,
        extraSupportedClouds):
    """Provisions VMs on the provider side and creates a k8s cluster with them.

    Parameters:
        test (str): Indicates the test for which to provision the cluster
        nodes (int): Number of nodes the cluster must contain.
        flavor (str): Flavor to be used for the VMs.
        extraInstanceConfig (str): Extra HCL code to configure VM
        toLog (str): File to which write the log msg.
        configs (dict): Object containing configs.yaml's configurations.
        testsRoot (str):
        retry ():
        instanceDefinition ():
        credentials ():
        dependencies ():
        baseCWD ():
        provDict ():
        extraSupportedClouds ():

    Returns:
        bool: True if the cluster was succesfully provisioned. False otherwise.
        str: Message informing of the provisionment task result.
    """

    templatesPath = "templates/"
    if configs["providerName"] in extraSupportedClouds:
        templatesPath += configs["providerName"]
    else:
        templatesPath += "general"

    mainTfDir = testsRoot + test
    kubeconfig = "config"
    if test == "shared":
        flavor = configs["flavor"]
        mainTfDir = testsRoot + "sharedCluster"
        os.makedirs(mainTfDir, exist_ok=True)
        kubeconfig = "~/.kube/config"

    if retry is None:
        randomId = ''.join(
            random.SystemRandom().choice(
                string.ascii_lowercase +
                string.digits) for _ in range(4))  # One randomId per cluster
        nodeName = ("kubenode-%s-%s-%s" %
                    (configs["providerName"], test, str(randomId))).lower()

        # ---------------- delete TF stuff from previous run if existing
        cleanupTF(mainTfDir)

        # ---------------- manage general variables

        openUserDefault = "root"
        msgExcept = "WARNING: using default user '%s' for ssh connections (running on %s)" % (openUserDefault,configs["providerName"])
        openUser = tryTakeFromYaml(configs, "openUser", openUserDefault, msgExcept=msgExcept)

        variables = loadFile("templates/general/variables.tf",
                             required=True).replace(
            "NODES_PH", str(nodes)).replace(
            "PATH_TO_KEY_VALUE", str(configs["pathToKey"])).replace(
            "KUBECONFIG_DST", kubeconfig).replace(
            "OPEN_USER_PH", openUser).replace(
            "NAME_PH", nodeName)
        variables = stackVersioning(variables, configs)

        if configs["providerName"] == "azurerm":

            # manage image related vars
            publisher = "OpenLogic" if configs["image"]["publisher"] is None \
                else configs["image"]["publisher"]
            offer = "CentOS" if configs["image"]["offer"] is None \
                else configs["image"]["offer"]
            sku = "7.5" if configs["image"]["sku"] is None \
                else configs["image"]["sku"]
            version = "latest" if configs["image"]["version"] is None \
                else configs["image"]["version"]

            # ---------------- main.tf: manage azure specific vars and add them
            variables = variables.replace(
                "SUBSCRIPTION_PH", configs['subscriptionId']).replace(
                "LOCATION_PH", configs['location']).replace(
                "PUB_SSH_PH", configs['pubSSH']).replace(
                "RGROUP_PH", configs['resourceGroupName']).replace(
                "RANDOMID_PH", randomId).replace(
                "VM_SIZE_PH", flavor).replace(
                "SECGROUPID_PH", configs['securityGroupID']).replace(
                "SUBNETID_PH", configs['subnetId']).replace(
                "PUBLISHER_PH", publisher).replace(
                "OFFER_PH", offer).replace(
                "SKU_PH", str(sku)).replace(
                "VERSION_PH", str(version))
            writeToFile(mainTfDir + "/main.tf", variables, False)

            # ---------------- main.tf: add raw VMs provisioner
            rawProvisioning = loadFile(
                "%s/rawProvision.tf" % templatesPath, required=True)

        elif configs["providerName"] == "openstack":

            # manage optional related vars
            region = tryTakeFromYaml(configs, "region", "")
            availabilityZone = tryTakeFromYaml(configs, "availabilityZone", "")
            securityGroups = tryTakeFromYaml(configs, "securityGroups", "[]")

            # ---------------- main.tf: manage openstack specific vars and add them
            variables = variables.replace(
                "FLAVOR_PH", flavor).replace(
                "IMAGE_PH", configs['imageName']).replace(
                "KEY_PAIR_PH", configs['keyPair']).replace(
                "\"SEC_GROUPS_PH\"", securityGroups).replace(
                "REGION_PH", region).replace(
                "AV_ZONE_PH", availabilityZone)
            writeToFile(mainTfDir + "/main.tf", variables, False)

            # ---------------- main.tf: add raw VMs provisioner
            rawProvisioning = loadFile(
                "%s/rawProvision.tf" % templatesPath, required=True)

        elif configs["providerName"] == "google":

            # manage gpu related vars
            gpuCount = str(nodes) if test == "dlTest" else "0"
            gpuType = tryTakeFromYaml(configs, "gpuType", "")
            
            # ---------------- main.tf: manage google specific vars and add them
            variables = variables.replace(
                "CREDENTIALS_PATH_PH", configs['pathToCredentials']).replace(
                "PROJECT_PH", configs['project']).replace(
                "MACHINE_TYPE_PH", flavor).replace(
                "ZONE_PH", configs['zone']).replace(
                "IMAGE_PH", configs['image']).replace(
                "GPU_COUNT_PH", gpuCount).replace(
                "GPU_TYPE_PH", gpuType)
            writeToFile(mainTfDir + "/main.tf", variables, False)

            # ---------------- main.tf: add raw VMs provisioner
            rawProvisioning = loadFile(
                "%s/rawProvision.tf" % templatesPath, required=True)

        elif configs["providerName"] == "aws":

            # manage optional vars

            awsTemplate = "%s/rawProvision.tf" % templatesPath
            volumeSize = tryTakeFromYaml(configs, "volumeSize", "")
            if volumeSize is "":
                awsTemplate = "%s/rawProvision_noVolumeSize.tf" % templatesPath


            # ---------------- main.tf: manage aws specific vars and add them
            variables = variables.replace(
                "REGION_PH", configs['region']).replace(
                "SHARED_CREDENTIALS_FILE_PH", configs['sharedCredentialsFile']).replace(
                "INSTANCE_TYPE_PH", flavor).replace(
                "AMI_PH", configs['ami']).replace(
                "NAME_KEY_PH", configs['keyName']).replace(
                "VOLUME_SIZE_PH", str(volumeSize))
            writeToFile(mainTfDir + "/main.tf", variables, False)

            # ---------------- main.tf: add raw VMs provisioner
            rawProvisioning = loadFile(awsTemplate, required=True)

        elif configs["providerName"] == "cloudstack":

            # manage optional vars
            securityGroups = tryTakeFromYaml(configs, "securityGroups", "[]")
            diskSize = tryTakeFromYaml(configs, "diskSize", "")
            if diskSize is "":
                csTemplate = "%s/rawProvision_noDiskSize.tf" % templatesPath
            else:
                csTemplate = "%s/rawProvision.tf" % templatesPath

            # ---------------- main.tf: manage aws specific vars and add them
            variables = variables.replace(
                "CONFIG_PATH_PH", configs['configPath']).replace(
                "ZONE_PH", configs['zone']).replace(
                "EXO_SIZE_PH", flavor).replace(
                "TEMPLATE_PH", configs['template']).replace(
                "KEY_PAIR_PH", configs['keyPair']).replace(
                "\"SEC_GROUPS_PH\"", securityGroups).replace(
                "DISK_SIZE_PH", str(diskSize))
            writeToFile(mainTfDir + "/main.tf", variables, False)

            # ---------------- main.tf: add raw VMs provisioner
            rawProvisioning = loadFile(csTemplate, required=True)

        elif configs["providerName"] == "exoscale":

            # manage optional vars
            securityGroups = tryTakeFromYaml(configs, "securityGroups", "[]")

            # ---------------- main.tf: manage aws specific vars and add them
            variables = variables.replace(
                "CONFIG_PATH_PH", configs['configPath']).replace(
                "ZONE_PH", configs['zone']).replace(
                "EXO_SIZE_PH", flavor).replace(
                "TEMPLATE_PH", configs['template']).replace(
                "KEY_PAIR_PH", configs['keyPair']).replace(
                "\"SEC_GROUPS_PH\"", securityGroups).replace(
                "DISK_SIZE_PH", str(configs['diskSize']))
            writeToFile(mainTfDir + "/main.tf", variables, False)

            # ---------------- main.tf: add raw VMs provisioner
            rawProvisioning = loadFile(
                "%s/rawProvision.tf" % templatesPath, required=True)

        else:
            # ---------------- main.tf: add vars
            writeToFile(mainTfDir + "/main.tf", variables, False)

            # ---------------- main.tf: add raw VMs provisioner
            instanceDefinition = "%s \n %s" % (flavor, instanceDefinition.replace(
                "NAME_PH", "${var.instanceName}-${count.index}"
            ))

            if extraInstanceConfig:
                instanceDefinition += "\n" + extraInstanceConfig

            rawProvisioning = loadFile("%s/rawProvision.tf" % templatesPath).replace(
                "CREDENTIALS_PLACEHOLDER", credentials).replace(
                "DEPENDENCIES_PLACEHOLDER", dependencies.replace(
                    "DEP_COUNT_PH", "count = %s" % nodes)).replace(
                "PROVIDER_NAME", str(configs["providerName"])).replace(
                "PROVIDER_INSTANCE_NAME", str(
                    configs["providerInstanceName"])).replace(
                "NODE_DEFINITION_PLACEHOLDER", instanceDefinition)

        writeToFile(mainTfDir + "/main.tf", rawProvisioning, True)

        # ---------------- RUN TERRAFORM - phase 1: provision VMs
        if runTerraform(mainTfDir,
                        baseCWD,
                        test,
                        "Provisioning '%s' VMs..." % flavor) != 0:
            return False, provisionFailMsg

        # ---------------- main.tf: add root allower + k8s bootstraper
        bootstrap = loadFile("templates/general/bootstrap.tf", required=True)

        if openUser is "root":
            bootstrap = bootstrap.replace("ALLOW_ROOT_COUNT", "0")
        else:
            bootstrap = bootstrap.replace("ALLOW_ROOT_COUNT", "var.customCount")

        bootstrap = bootstrap.replace(
            "LIST_IP_GETTER", provDict[configs["providerName"]])

        writeToFile(mainTfDir + "/main.tf", bootstrap, True)

    # ---------------- RUN TERRAFORM - phase 2: bootstrap the k8s cluster
    if runTerraform(mainTfDir,
                    baseCWD,
                    test,
                    "...bootstraping Kubernetes cluster...") != 0:
        return False, bootstrapFailMsg % flavor

    # ---------------- wait for default service account to be ready and finish
    kubeconfig = "~/.kube/config" if test == "shared" else "%s/%s" % (
        mainTfDir, kubeconfig)

    while runCMD(
        'kubectl --kubeconfig %s get sa default' %
        kubeconfig,
            hideLogs=True) != 0:
        time.sleep(1)

    writeToFile(toLog, "...'%s' CLUSTER CREATED => STARTING TESTS\n" %
                flavor, True)

    return True, ""
