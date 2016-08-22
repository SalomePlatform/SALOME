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
import logging
import ConfigParser

from parseConfigFile import parseConfigFile
from parseConfigFile import convertEnvFileToConfigFile

import tempfile
import pickle
import subprocess
import platform

from salomeContextUtils import SalomeContextException

def usage():
  msg = '''\
Usage: salome [command] [options] [--config=<file,folder,...>]

Commands:
=========
    start           Starts a SALOME session (through virtual application)
    context         Initializes SALOME context.
    shell           Initializes SALOME context, and executes scripts passed
                    as command arguments
    connect         Connects a Python console to the active SALOME session
    kill <port(s)>  Terminate SALOME session running on given ports for current user
                    Port numbers must be separated by blank characters
    killall         Kill *all* SALOME running sessions for current user
    test            Run SALOME tests.
    info            Display some information about SALOME
    help            Show this message

If no command is given, default to start.

Command options:
================
    Use salome <command> --help to show help on command ; available for commands:
    start, shell, connect, test, info.

--config=<file,folder,...>
==========================
    Initialize SALOME context from a list of context files and/or a list
    of folders containing context files. The list is comma-separated, whithout
    any blank characters.
'''

  print msg
#

"""
The SalomeContext class in an API to configure SALOME context then
start SALOME using a single python command.

"""
class SalomeContext:
  """
  Initialize context from a list of configuration files
  identified by their names.
  These files should be in appropriate (new .cfg) format.
  However you can give old .sh environment files; in this case,
  the SalomeContext class will try to automatically convert them
  to .cfg format before setting the context.
  """
  def __init__(self, configFileNames=0):
    #it could be None explicitely (if user use multiples setVariable...for standalone)
    if configFileNames is None:
       return
    configFileNames = configFileNames or []
    if len(configFileNames) == 0:
      raise SalomeContextException("No configuration files given")

    reserved=['PATH', 'DYLD_LIBRARY_PATH', 'LD_LIBRARY_PATH', 'PYTHONPATH', 'MANPATH', 'PV_PLUGIN_PATH', 'INCLUDE', 'LIBPATH', 'SALOME_PLUGINS_PATH']
    for filename in configFileNames:
      basename, extension = os.path.splitext(filename)
      if extension == ".cfg":
        self.__setContextFromConfigFile(filename, reserved)
      elif extension == ".sh":
        #new convert procedures, temporary could be use not to be automatically deleted
        #temp = tempfile.NamedTemporaryFile(suffix='.cfg', delete=False)
        temp = tempfile.NamedTemporaryFile(suffix='.cfg')
        try:
          convertEnvFileToConfigFile(filename, temp.name, reserved)
          self.__setContextFromConfigFile(temp.name, reserved)
          temp.close()
        except (ConfigParser.ParsingError, ValueError) as e:
          self.getLogger().error("Invalid token found when parsing file: %s\n"%(filename))
          temp.close()
          sys.exit(1)
      else:
        self.getLogger().warning("Unrecognized extension for configuration file: %s", filename)
  #

  def __loadMPI(self, module_name):
    print "Trying to load MPI module: %s..."%module_name,
    try:
      out, err = subprocess.Popen(["modulecmd", "python", "load", module_name], stdout=subprocess.PIPE).communicate()
      exec out # define specific environment variables
      print " OK"
    except:
      print " ** Failed **"
      pass
  #

  def runSalome(self, args):
    import os
    # Run this module as a script, in order to use appropriate Python interpreter
    # according to current path (initialized from context files).
    mpi_module_option = "--with-mpi-module="
    mpi_module = [x for x in args if x.startswith(mpi_module_option)]
    if mpi_module:
      mpi_module = mpi_module[0][len(mpi_module_option):]
      self.__loadMPI(mpi_module)
      args = [x for x in args if not x.startswith(mpi_module_option)]
    else:
      mpi_module = os.getenv("SALOME_MPI_MODULE_NAME", None)
      if mpi_module:
        self.__loadMPI(mpi_module)

    absoluteAppliPath = os.getenv('ABSOLUTE_APPLI_PATH','')
    env_copy = os.environ.copy()
    proc = subprocess.Popen(['python', os.path.join(absoluteAppliPath,"bin","salome","salomeContext.py"), pickle.dumps(self), pickle.dumps(args)], shell=False, close_fds=True, env=env_copy)
    msg = proc.communicate()
    return msg, proc.returncode
  #

  """Append value to PATH environment variable"""
  def addToPath(self, value):
    self.addToVariable('PATH', value)
  #

  """Append value to LD_LIBRARY_PATH environment variable"""
  def addToLdLibraryPath(self, value):
    self.addToVariable('LD_LIBRARY_PATH', value)
  #

  """Append value to DYLD_LIBRARY_PATH environment variable"""
  def addToDyldLibraryPath(self, value):
    self.addToVariable('DYLD_LIBRARY_PATH', value)
  #

  """Append value to PYTHONPATH environment variable"""
  def addToPythonPath(self, value):
    self.addToVariable('PYTHONPATH', value)
  #

  """Set environment variable to value"""
  def setVariable(self, name, value, overwrite=False):
    env = os.getenv(name, '')
    if env and not overwrite:
      self.getLogger().warning("Environment variable already existing (and not overwritten): %s=%s", name, value)
      return

    if env:
      self.getLogger().warning("Overwriting environment variable: %s=%s", name, value)

    value = os.path.expandvars(value) # expand environment variables
    self.getLogger().debug("Set environment variable: %s=%s", name, value)
    os.environ[name] = value
  #

  """Unset environment variable"""
  def unsetVariable(self, name):
    if os.environ.has_key(name):
      del os.environ[name]
  #

  """Append value to environment variable"""
  def addToVariable(self, name, value, separator=os.pathsep):
    if value == '':
      return

    value = os.path.expandvars(value) # expand environment variables
    self.getLogger().debug("Add to %s: %s", name, value)
    env = os.getenv(name, None)
    if env is None:
      os.environ[name] = value
    else:
      os.environ[name] = value + separator + env
  #

  ###################################
  # This begins the private section #
  ###################################

  def __parseArguments(self, args):
    if len(args) == 0 or args[0].startswith("-"):
      return None, args

    command = args[0]
    options = args[1:]

    availableCommands = {
      'start'   : '_runAppli',
      'context' : '_setContext',
      'shell'   : '_runSession',
      'connect' : '_runConsole',
      'kill'    : '_kill',
      'killall' : '_killAll',
      'test'    : '_runTests',
      'info'    : '_showInfo',
      'help'    : '_usage',
      'coffee'  : '_makeCoffee',
      'car'     : '_getCar',
      }

    if not command in availableCommands.keys():
      command = "start"
      options = args

    return availableCommands[command], options
  #

  """
  Run SALOME!
  Args consist in a mandatory command followed by optionnal parameters.
  See usage for details on commands.
  """
  def _startSalome(self, args):
    import os
    import sys
    try:
      from setenv import add_path
      absoluteAppliPath = os.getenv('ABSOLUTE_APPLI_PATH')
      path = os.path.realpath(os.path.join(absoluteAppliPath, "bin", "salome"))
      add_path(path, "PYTHONPATH")
      path = os.path.realpath(os.path.join(absoluteAppliPath, "bin", "salome", "appliskel"))
      add_path(path, "PYTHONPATH")

    except:
      pass

    command, options = self.__parseArguments(args)
    sys.argv = options

    if command is None:
      if args and args[0] in ["-h","--help","help"]:
        usage()
        sys.exit(0)
      # try to default to "start" command
      command = "_runAppli"

    try:
      res = getattr(self, command)(options) # run appropriate method
      return res or (None, None)
    except SystemExit, returncode:
      if returncode != 0:
        self.getLogger().warning("SystemExit %s in method %s.", returncode, command)
      sys.exit(returncode)
    except StandardError:
      self.getLogger().error("Unexpected error:")
      import traceback
      traceback.print_exc()
      sys.exit(1)
    except SalomeContextException, e:
      self.getLogger().error(e)
      sys.exit(1)
  #

  def __setContextFromConfigFile(self, filename, reserved=None):
    if reserved is None:
      reserved = []
    try:
      unsetVars, configVars, reservedDict = parseConfigFile(filename, reserved)
    except SalomeContextException, e:
      msg = "%s"%e
      file_dir = os.path.dirname(filename)
      file_base = os.path.basename(filename)
      base_no_ext, ext = os.path.splitext(file_base)
      sh_file = os.path.join(file_dir, base_no_ext+'.sh')
      if ext == ".cfg" and os.path.isfile(sh_file):
        msg += "Found similar %s file; trying to parse this one instead..."%(base_no_ext+'.sh')
        temp = tempfile.NamedTemporaryFile(suffix='.cfg')
        try:
          convertEnvFileToConfigFile(sh_file, temp.name, reserved)
          self.__setContextFromConfigFile(temp.name, reserved)
          msg += "OK\n"
          self.getLogger().warning(msg)
          temp.close()
          return
        except (ConfigParser.ParsingError, ValueError) as e:
          msg += "Invalid token found when parsing file: %s\n"%(sh_file)
          self.getLogger().error(msg)
          temp.close()
          sys.exit(1)
      else:
        self.getLogger().error(msg)
        sys.exit(1)

    # unset variables
    for var in unsetVars:
      self.unsetVariable(var)

    # set context
    for reserved in reservedDict:
      a = filter(None, reservedDict[reserved]) # remove empty elements
      a = [ os.path.realpath(x) for x in a ]
      reformattedVals = os.pathsep.join(a)
      if reserved in ["INCLUDE", "LIBPATH"]:
        self.addToVariable(reserved, reformattedVals, separator=' ')
      else:
        self.addToVariable(reserved, reformattedVals)
      pass

    for key,val in configVars:
      self.setVariable(key, val, overwrite=True)
      pass

    pythonpath = os.getenv('PYTHONPATH','').split(os.pathsep)
    pythonpath = [ os.path.realpath(x) for x in pythonpath ]
    sys.path[:0] = pythonpath
  #

  def _runAppli(self, args=None):
    if args is None:
      args = []
    # Initialize SALOME environment
    sys.argv = ['runSalome'] + args
    import setenv
    setenv.main(True)

    import runSalome
    runSalome.runSalome()
  #

  def _setContext(self, args=None):
    salome_context_set = os.getenv("SALOME_CONTEXT_SET")
    if salome_context_set:
      print "***"
      print "*** SALOME context has already been set."
      print "*** Enter 'exit' (only once!) to leave SALOME context."
      print "***"
      return

    os.environ["SALOME_CONTEXT_SET"] = "yes"
    print "***"
    print "*** SALOME context is now set."
    print "*** Enter 'exit' (only once!) to leave SALOME context."
    print "***"

    cmd = ["/bin/bash"]
    proc = subprocess.Popen(cmd, shell=False, close_fds=True)
    return proc.communicate()
  #

  def _runSession(self, args=None):
    if args is None:
      args = []
    sys.argv = ['runSession'] + args
    import runSession
    params, args = runSession.configureSession(args, exe="salome shell")

    sys.argv = ['runSession'] + args
    import setenv
    setenv.main(True)

    return runSession.runSession(params, args)
  #

  def _runConsole(self, args=None):
    if args is None:
      args = []
    # Initialize SALOME environment
    sys.argv = ['runConsole']
    import setenv
    setenv.main(True)

    import runConsole
    return runConsole.connect(args)
  #

  def _kill(self, args=None):
    if args is None:
      args = []
    ports = args
    if not ports:
      print "Port number(s) not provided to command: salome kill <port(s)>"
      return

    from multiprocessing import Process
    from killSalomeWithPort import killMyPort
    import tempfile
    for port in ports:
      with tempfile.NamedTemporaryFile():
        p = Process(target = killMyPort, args=(port,))
        p.start()
        p.join()
    pass
  #

  def _killAll(self, unused=None):
    try:
      import PortManager # mandatory
      from multiprocessing import Process
      from killSalomeWithPort import killMyPort
      ports = PortManager.getBusyPorts()

      if ports:
        import tempfile
        for port in ports:
          with tempfile.NamedTemporaryFile():
            p = Process(target = killMyPort, args=(port,))
            p.start()
            p.join()
    except ImportError:
      from killSalome import killAllPorts
      killAllPorts()
      pass
  #

  def _runTests(self, args=None):
    if args is None:
      args = []
    sys.argv = ['runTests']
    import setenv
    setenv.main(True)

    import runTests
    return runTests.runTests(args, exe="salome test")
  #

  def _showInfo(self, args=None):
    if args is None:
      args = []

    usage = "Usage: salome info [options]"
    epilog  = """\n
Display some information about SALOME.\n
Available options are:
    -p,--ports        Show list of busy ports (running SALOME instances).
    -v,--version      Show running SALOME version.
    -h,--help         Show this message.
"""
    if not args:
      args = ["--version"]

    if "-h" in args or "--help" in args:
      print usage + epilog
      return

    if "-p" in args or "--ports" in args:
      import PortManager
      ports = PortManager.getBusyPorts()
      print "SALOME instances are running on ports:", ports
      if ports:
        print "Last started instance on port %s"%ports[-1]

    if "-v" in args or "--version" in args:
      print "Running with python", platform.python_version()
      self._runAppli(["--version"])
  #

  def _usage(self, unused=None):
    usage()
  #

  def _makeCoffee(self, unused=None):
    print "                        ("
    print "                          )     ("
    print "                   ___...(-------)-....___"
    print "               .-\"\"       )    (          \"\"-."
    print "         .-\'``\'|-._             )         _.-|"
    print "        /  .--.|   `\"\"---...........---\"\"`   |"
    print "       /  /    |                             |"
    print "       |  |    |                             |"
    print "        \\  \\   |                             |"
    print "         `\\ `\\ |                             |"
    print "           `\\ `|            SALOME           |"
    print "           _/ /\\            4 EVER           /"
    print "          (__/  \\             <3            /"
    print "       _..---\"\"` \\                         /`\"\"---.._"
    print "    .-\'           \\                       /          \'-."
    print "   :               `-.__             __.-\'              :"
    print "   :                  ) \"\"---...---\"\" (                 :"
    print "    \'._               `\"--...___...--\"`              _.\'"
    print "      \\\"\"--..__                              __..--\"\"/"
    print "       \'._     \"\"\"----.....______.....----\"\"\"     _.\'"
    print "          `\"\"--..,,_____            _____,,..--\"\"`"
    print "                        `\"\"\"----\"\"\"`"
    print ""
    print "                    SALOME is working for you; what else?"
    print ""
    sys.exit(0)
  #

  def _getCar(self, unused=None):
    print "                                              _____________"
    print "                                  ..---:::::::-----------. ::::;;."
    print "                               .\'\"\"\"\"\"\"                  ;;   \\  \":."
    print "                            .\'\'                          ;     \\   \"\\__."
    print "                          .\'                            ;;      ;   \\\\\";"
    print "                        .\'                              ;   _____;   \\\\/"
    print "                      .\'                               :; ;\"     \\ ___:\'."
    print "                    .\'--...........................    : =   ____:\"    \\ \\"
    print "               ..-\"\"                               \"\"\"\'  o\"\"\"     ;     ; :"
    print "          .--\"\"  .----- ..----...    _.-    --.  ..-\"     ;       ;     ; ;"
    print "       .\"\"_-     \"--\"\"-----\'\"\"    _-\"        .-\"\"         ;        ;    .-."
    print "    .\'  .\'   SALOME             .\"         .\"              ;       ;   /. |"
    print "   /-./\'         4 EVER <3    .\"          /           _..  ;       ;   ;;;|"
    print "  :  ;-.______               /       _________==.    /_  \\ ;       ;   ;;;;"
    print "  ;  / |      \"\"\"\"\"\"\"\"\"\"\".---.\"\"\"\"\"\"\"          :    /\" \". |;       ; _; ;;;"
    print " /\"-/  |                /   /                  /   /     ;|;      ;-\" | ;\';"
    print ":-  :   \"\"\"----______  /   /              ____.   .  .\"\'. ;;   .-\"..T\"   ."
    print "\'. \"  ___            \"\":   \'\"\"\"\"\"\"\"\"\"\"\"\"\"\"    .   ; ;    ;; ;.\" .\"   \'--\""
    print " \",   __ \"\"\"  \"\"---... :- - - - - - - - - \' \'  ; ;  ;    ;;\"  .\""
    print "  /. ;  \"\"\"---___                             ;  ; ;     ;|.\"\""
    print " :  \":           \"\"\"----.    .-------.       ;   ; ;     ;:"
    print "  \\  \'--__               \\   \\        \\     /    | ;     ;;"
    print "   \'-..   \"\"\"\"---___      :   .______..\\ __/..-\"\"|  ;   ; ;"
    print "       \"\"--..       \"\"\"--\"        m l s         .   \". . ;"
    print "             \"\"------...                  ..--\"\"      \" :"
    print "                        \"\"\"\"\"\"\"\"\"\"\"\"\"\"\"\"\"\"    \\        /"
    print "                                               \"------\""
    print ""
    print "                                Drive your simulation properly with SALOME!"
    print ""
    sys.exit(0)
  #

  # Add the following two methods since logger is not pickable
  # Ref: http://stackoverflow.com/questions/2999638/how-to-stop-attributes-from-being-pickled-in-python
  def __getstate__(self):
    d = dict(self.__dict__)
    if hasattr(self, '_logger'):
      del d['_logger']
    return d
  #
  def __setstate__(self, d):
    self.__dict__.update(d) # I *think* this is a safe way to do it
  #
  # Excluding self._logger from pickle operation imply using the following method to access logger
  def getLogger(self):
    if not hasattr(self, '_logger'):
      self._logger = logging.getLogger(__name__)
      #self._logger.setLevel(logging.DEBUG)
      #self._logger.setLevel(logging.WARNING)
      self._logger.setLevel(logging.ERROR)
    return self._logger
  #

if __name__ == "__main__":
  if len(sys.argv) == 3:
    context = pickle.loads(sys.argv[1])
    args = pickle.loads(sys.argv[2])

    (out, err) = context._startSalome(args)
    if out:
      sys.stdout.write(out)
    if err:
      sys.stderr.write(err)
  else:
    usage()
#