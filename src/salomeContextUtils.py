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

def __getEnvironmentFileNames(args, optionPrefix, checkExistence):
  # special case: extra configuration/environment files are provided by user
  # Search for command-line argument(s) <optionPrefix>=file1,file2,..., filen
  # Search for command-line argument(s) <optionPrefix>=dir1,dir2,..., dirn
  configArgs = [ str(x) for x in args if str(x).startswith(optionPrefix) ]

  args = [ x for x in args if not x.startswith(optionPrefix) ]
  allLists = [ x.replace(optionPrefix, '') for x in configArgs ]

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

def __validate_pair(ob):
  try:
    if not (len(ob) == 2):
      #print "Unexpected result:", ob
      raise ValueError
  except:
    return False
  return True
#
def __get_environment_from_batch_command(env_cmd, initial=None):
  """
  Take a command (either a single command or list of arguments)
  and return the environment created after running that command.
  Note that if the command must be a batch file or .cmd file, or the
  changes to the environment will not be captured.

  If initial is supplied, it is used as the initial environment passed
  to the child process.
  """
  #if not isinstance(env_cmd, (list, tuple)):
  #    env_cmd = [env_cmd]
  # construct the command that will alter the environment
  #env_cmd = subprocess.list2cmdline(env_cmd)
  # create a tag so we can tell in the output when the proc is done
  tag = 'Done running command'
  # construct a command to do accomplish this
  cmd = '{env_cmd} && echo "{tag}"'.format(**vars())

  # launch the process
  proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=initial, shell=True)
  # parse the output sent to stdout
  lines = proc.stdout
  # consume whatever output occurs until the tag is reached
  #consume(itertools.takewhile(lambda l: tag not in l, lines))
  # define a way to handle each KEY=VALUE line
  handle_line = lambda l: l.rstrip().split('=',1)
  # parse key/values into pairs
  #pairs = map(handle_line, lines)
  pairs = []
  cpt = 0
  while True:
    line = lines.readline()
    cpt = cpt+1
    if tag in line or cpt > 1000:
      break
    if line:
      pairs.append(line.rstrip().split('=',1))
  # make sure the pairs are valid
  valid_pairs = filter(__validate_pair, pairs)
  # construct a dictionary of the pairs
  result = dict(valid_pairs)
  # let the process finish
  proc.communicate()
  return result
#
def __subtract(ref, dic):
  result = {}
  for key,val in ref.items():
    if not dic.has_key(key):
      result[key] = val
    else:
      # compare values types
      if (type(dic[key]) != type(val)):
        result[key] = val
      else:
        # compare values
        if isinstance(val, basestring):
          tolist1 = dic[key].split(os.pathsep)
          tolist2 = val.split(os.pathsep)
          diff = list(set(tolist2)-set(tolist1))
          if diff:
            result[key] = os.pathsep.join(diff)
        else:
          result[key] = val

  return result
#

def getConfigFileNames(args, checkExistence=False):
  configOptionPrefix = "--config="
  configArgs = [ str(x) for x in args if str(x).startswith(configOptionPrefix) ]
  if len(configArgs) == 0:
    configFileNames, unexist1 = __getConfigFileNamesDefault(), []
  else:
    # get configuration filenames
    configFileNames, args, unexist1 = __getEnvironmentFileNames(args, configOptionPrefix, checkExistence)

  # get extra environment
  extraEnvFileNames, args, unexist2 = __getEnvironmentFileNames(args, "--extra_env=", checkExistence)
  before = __get_environment_from_batch_command("env")
  after = {}
  for filename in extraEnvFileNames:
    after.update(__get_environment_from_batch_command(filename))
    pass

  extraEnv = __subtract(after,before)
  return configFileNames, extraEnv, args, unexist1+unexist2
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
  def __init__(self, script=None, args=None, out=None):
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

def getShortAndExtraArgs(args=None):
  if args is None:
    args = []
  try:
    pos = args.index("--") # raise a ValueError if not found
    short_args = args[:pos]
    extra_args = args[pos:] # include "--"
  except ValueError:
    short_args = args
    extra_args = []
    pass

  return short_args, extra_args
#

# Return an array of ScriptAndArgs objects
def getScriptsAndArgs(args=None, searchPathList=None):
  if args is None:
    args = []
  short_args, extra_args = getShortAndExtraArgs(args)
  args = short_args

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

  if len(extra_args) > 1: # syntax: -- program [options] [arguments]
    command = extra_args[1]
    command_args = extra_args[2:]
    scriptArgs.append(ScriptAndArgs(script=command, args=command_args))
    pass

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

# Ensure OMNIORB_USER_PATH is defined. This variable refers to a folder in which
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