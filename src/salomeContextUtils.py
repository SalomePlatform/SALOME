#! /usr/bin/env python

# Copyright (C) 2013-2015  CEA/DEN, EDF R&D, OPEN CASCADE
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307 USA
#
# See http://www.salome-platform.org/ or email : webmaster.salome@opencascade.com
#

import os
import sys
import glob
import subprocess
import re
import socket
import json

"""
Define a specific exception class to manage exceptions related to SalomeContext
"""
class SalomeContextException(Exception):
  """Report error messages to the user interface of SalomeContext."""
#

def __listDirectory(path):
  allFiles = []
  for root, dirs, files in os.walk(path):
    cfgFiles = glob.glob(os.path.join(root,'*.cfg'))
    allFiles += cfgFiles

    shFiles = glob.glob(os.path.join(root,'*.sh'))
    for f in shFiles:
      no_ext = os.path.splitext(f)[0]
      if not os.path.isfile(no_ext+".cfg"):
        allFiles.append(f)

  return allFiles
#

def __getConfigFileNamesDefault():
  absoluteAppliPath = os.getenv('ABSOLUTE_APPLI_PATH','')
  if not absoluteAppliPath:
    return []

  envdDir = absoluteAppliPath + '/env.d'
  if not os.path.isdir(envdDir):
    return []

  return __listDirectory(envdDir)
#

def getConfigFileNames(args, checkExistence=False):
  # special case: configuration files are provided by user
  # Search for command-line argument(s) --config=file1,file2,..., filen
  # Search for command-line argument(s) --config=dir1,dir2,..., dirn
  configOptionPrefix = "--config="
  configArgs = [ str(x) for x in args if str(x).startswith(configOptionPrefix) ]

  if len(configArgs) == 0:
    return __getConfigFileNamesDefault(), args, []

  args = [ x for x in args if not x.startswith(configOptionPrefix) ]
  allLists = [ x.replace(configOptionPrefix, '') for x in configArgs ]

  configFileNames = []
  unexisting = []
  for currentList in allLists:
    elements = currentList.split(',')
    for elt in elements:
      elt = os.path.realpath(os.path.expanduser(elt))
      if os.path.isdir(elt):
        configFileNames += __listDirectory(elt)
      else:
        if checkExistence and not os.path.isfile(elt):
          unexisting += [elt]
        else:
          configFileNames += [elt]

  return configFileNames, args, unexisting
#

def __getScriptPath(scriptName, searchPathList):
  scriptName = os.path.expanduser(scriptName)
  if os.path.isabs(scriptName):
    return scriptName

  if searchPathList is None or len(searchPathList) == 0:
    return None

  for path in searchPathList:
    fullName = os.path.join(path, scriptName)
    if os.path.isfile(fullName) or os.path.isfile(fullName+".py"):
      return fullName

  return None
#

class ScriptAndArgs:
  # script: the command to be run, e.g. python <script.py>
  # args: its input parameters
  # out: its output parameters
  def __init__(self, script = None, args = None, out = None):
    self.script = script
    self.args = args
    self.out = out
  #
  def __repr__(self):
    msg = "\n# Script: %s\n"%self.script
    msg += "     * Input: %s\n"%self.args
    msg += "     * Output: %s\n"%self.out
    return msg
  #
#
class ScriptAndArgsObjectEncoder(json.JSONEncoder):
  def default(self, obj):
    if isinstance(obj, ScriptAndArgs):
      # to be easily parsed in GUI module (SalomeApp_Application)
      # Do not export output arguments
      return {obj.script:obj.args or []}
    else:
      return json.JSONEncoder.default(self, obj)
#

# Return an array of ScriptAndArgs objects
def getScriptsAndArgs(args=None, searchPathList=None):
  if args is None:
    args = []
  if searchPathList is None:
    searchPathList = sys.path

  # Syntax of args: script.py [args:a1,a2=val,an] ... script.py [args:a1,a2=val,an]
  scriptArgs = []
  currentKey = None
  argsPrefix = "args:"
  outPrefix = "out:"
  callPython = False
  afterArgs = False
  currentScript = None

  for i in range(len(args)):
    elt = os.path.expanduser(args[i])
    isDriver = (elt == "driver") # special case for YACS scheme execution

    if elt.startswith(argsPrefix):
      if not currentKey or callPython:
        raise SalomeContextException("args list must follow corresponding script file in command line.")
      elt = elt.replace(argsPrefix, '')
      scriptArgs[len(scriptArgs)-1].args = [os.path.expanduser(x) for x in elt.split(",")]
      currentKey = None
      callPython = False
      afterArgs = True
    elif elt.startswith(outPrefix):
      if (not currentKey and not afterArgs) or callPython:
        raise SalomeContextException("out list must follow both corresponding script file and its args in command line.")
      elt = elt.replace(outPrefix, '')
      scriptArgs[len(scriptArgs)-1].out = [os.path.expanduser(x) for x in elt.split(",")]
      currentKey = None
      callPython = False
      afterArgs = False
    elif elt.startswith("python"):
      callPython = True
      afterArgs = False
    else:
      if not os.path.isfile(elt) and not os.path.isfile(elt+".py"):
        eltInSearchPath = __getScriptPath(elt, searchPathList)
        if eltInSearchPath is None or (not os.path.isfile(eltInSearchPath) and not os.path.isfile(eltInSearchPath+".py")):
          if elt[-3:] == ".py":
            raise SalomeContextException("Script not found: %s"%elt)
          scriptArgs.append(ScriptAndArgs(script=elt))
          continue
        elt = eltInSearchPath

      if elt[-4:] != ".hdf":
        if elt[-3:] == ".py" or isDriver:
          currentScript = os.path.abspath(elt)
        elif os.path.isfile(elt+".py"):
          currentScript = os.path.abspath(elt+".py")
        else:
          currentScript = os.path.abspath(elt) # python script not necessary has .py extension
        pass

      if currentScript and callPython:
        currentKey = "python "+currentScript
        scriptArgs.append(ScriptAndArgs(script=currentKey))
        callPython = False
      elif currentScript:
        if isDriver:
          currentKey = currentScript
          scriptArgs.append(ScriptAndArgs(script=currentKey))
          callPython = False
        elif not os.access(currentScript, os.X_OK):
          currentKey = "python "+currentScript
          scriptArgs.append(ScriptAndArgs(script=currentKey))
        else:
          ispython = False
          try:
            fn = open(currentScript)
            for i in xrange(10): # read only 10 first lines
              ln = fn.readline()
              if re.search("#!.*python"):
                ispython = True
                break
              pass
            fn.close()
          except:
            pass
          if not ispython and currentScript[-3:] == ".py":
            currentKey = "python "+currentScript
          else:
            currentKey = currentScript
            pass
          scriptArgs.append(ScriptAndArgs(script=currentKey))
      # CLOSE elif currentScript
      afterArgs = False
  # end for loop
  return scriptArgs
#

# Formatting scripts and args as a Bash-like command-line:
# script1.py [args] ; script2.py [args] ; ...
# scriptArgs is a list of ScriptAndArgs objects; their output parameters are omitted
def formatScriptsAndArgs(scriptArgs=None):
    if scriptArgs is None:
      return ""
    commands = []
    for sa_obj in scriptArgs:
      cmd = sa_obj.script
      if sa_obj.args:
        cmd = " ".join([cmd]+sa_obj.args)
      commands.append(cmd)

    sep = " ; "
    if sys.platform == "win32":
      sep = " & "
    command = sep.join(["%s"%x for x in commands])
    return command
#

# Ensure OMNIORB_USER_PATH is defined. This variable refers to a the folder in which
# SALOME will write omniOrb configuration files.
# If OMNIORB_USER_PATH is already set, only checks write access to associated directory ;
# an exception is raised if check fails. It allows users for choosing a specific folder.
# Else the function sets OMNIORB_USER_PATH this way:
# - If APPLI environment variable is set, OMNIORB_USER_PATH is set to ${APPLI}/USERS.
#   The function does not check USERS folder existence or write access. This folder
#   must exist ; this is the case if SALOME virtual application has been created using
#   appli_gen.py script.
# - Else OMNIORB_USER_PATH is set to user home directory.
def setOmniOrbUserPath():
  omniorbUserPath = os.getenv("OMNIORB_USER_PATH")
  if omniorbUserPath:
    if not os.access(omniorbUserPath, os.W_OK):
      raise Exception("Unable to get write access to directory: %s"%omniorbUserPath)
    pass
  else:
    homePath = os.path.realpath(os.path.expanduser('~'))
    #defaultOmniorbUserPath = os.path.join(homePath, ".salomeConfig/USERS")
    defaultOmniorbUserPath = homePath
    if os.getenv("APPLI"):
      defaultOmniorbUserPath = os.path.join(homePath, os.getenv("APPLI"), "USERS")
      pass
    os.environ["OMNIORB_USER_PATH"] = defaultOmniorbUserPath
#

def getHostname():
  return socket.gethostname().split('.')[0]
#
