#! /bin/sh
#
# Copyright (C) 2003-2014 Intel Corporation.  All Rights Reserved.
# 
# The source code contained or described herein and all documents
# related to the source code ("Material") are owned by Intel Corporation
# or its suppliers or licensors.  Title to the Material remains with
# Intel Corporation or its suppliers and licensors.  The Material is
# protected by worldwide copyright and trade secret laws and treaty
# provisions.  No part of the Material may be used, copied, reproduced,
# modified, published, uploaded, posted, transmitted, distributed, or
# disclosed in any way without Intel's prior express written permission.
# 
# No license under any patent, copyright, trade secret or other
# intellectual property right is granted to or conferred upon you by
# disclosure or delivery of the Materials, either expressly, by
# implication, inducement, estoppel or otherwise.  Any license under
# such intellectual property rights must be express and approved by
# Intel in writing.
#

I_MPI_ROOT_TEMP=`which ${0}`
I_MPI_ROOT=$(dirname "$I_MPI_ROOT_TEMP")/../../; export I_MPI_ROOT

if [ -z "${PATH}" ]
then
    PATH="${I_MPI_ROOT}/ia32/bin"; export PATH
else
    PATH="${I_MPI_ROOT}/ia32/bin:${PATH}"; export PATH
fi

if [ -z "${LD_LIBRARY_PATH}" ]
then
    LD_LIBRARY_PATH="${I_MPI_ROOT}/ia32/lib"; export LD_LIBRARY_PATH
else
    LD_LIBRARY_PATH="${I_MPI_ROOT}/ia32/lib:${LD_LIBRARY_PATH}"; export LD_LIBRARY_PATH
fi

if [ -z "${MANPATH}" ]
then
    if [ `uname -m` = "k1om" ]
    then
        MANPATH="${I_MPI_ROOT}/man"; export MANPATH
    else
        MANPATH="${I_MPI_ROOT}/man":$(manpath); export MANPATH
    fi
else
    MANPATH="${I_MPI_ROOT}/man:${MANPATH}"; export MANPATH
fi