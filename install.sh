#!/usr/bin/env bash
#########################################################################
# File Name: install.sh
# Author: Chufuyuan
# Mail: chufuyuan@live.cn
# Created Time: Tue Dec 20 23:50:23 2016
#########################################################################

WS=$(cd $(dirname $0);pwd)

pip install virtualenv

cd $WS
virtualenv env

. env/bin/activate
pip install -r requirements.txt
