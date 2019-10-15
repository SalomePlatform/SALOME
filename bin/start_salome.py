#!/usr/bin/env python3
# lightweight salome launcher
import subprocess
import os
import glob
import json
#
import orbmodule
from searchFreePort import searchFreePort
import SALOME
import SALOME_ModuleCatalog
#
# define supported options
# [PYTHON_FILE [args] [PYTHON_FILE [args]...]]
usage = """Usage: salome.py [options] [python_file [args]] [python_file [args]] ...
       Python file arguments, if any, must be comma-separated and prefixed by args 
       (without blank characters and quotes),  e.g. myscript.py args:arg1,arg2=val
       
       Starts salome and optionnally executes python scripts provided as trailing arguments"""
from optparse import OptionParser
parser = OptionParser(usage=usage)
parser.add_option("-g", "--gui", action="store_true", dest="gui", default=False, 
                  help="Launch salome servers and start gui")
parser.add_option("-t", "--tui", action="store_true", dest="tui", default=False, 
                  help="Launch salome servers")
parser.add_option("-e", "--environ", action="store_true", dest="env", default=False, 
                  help="return a bash shell with Salome environement set")

# main programm
def main():
    (options, args) = parser.parse_args()
    if not (options.gui or options.tui or options.env):
        # all options are set to false! activate gui option
        options.gui=True

    options.extra_args=None
    if args: # parse optionnal python scripts args
        options.extra_args=parse_extra_args(args)
        
    if options.env:
        # return 
        return bash_shell()

    if options.tui or options.gui:
        clt=start_salome(options)
        #if clt != None:
        #    print(" --- registered objects tree in Naming Service ---")
        #    clt.showNS()

def parse_extra_args(args):
    # these extra args represent python script files with optionnally their arguments
    extra_args=[] # build a list of dicts (the form required by salome session server)
    while args:
        # pull first arg, check it is a file
        pyfilename=args[0]
        pyargs=[]
        args=args[1:]
        if not os.path.isfile(pyfilename):
            continue # if the arg is not a file name we skip it
        if args and args[0].startswith("args:"):
            #if the next arg is related to pyscript, pull it and process it
            pyargs=args[0][5:].split(",")
            args=args[1:]
        extra_args.append({pyfilename:pyargs})
    return extra_args

def bash_shell():
    cmd = ["/bin/bash"]
    proc = subprocess.Popen(cmd, shell=False, close_fds=True)
    proc.communicate()
    return proc.returncode

def start_salome(options):
    clt=start_orb()

    # Launch Registry Server, and wait for it available in Naming Service
    RegistryServer().run()
    clt.waitNS("/Registry")
    
    # Launch Module Catalog Server, and wait for it available in Naming Service
    CatalogServer().run()
    clt.waitNS("/Kernel/ModulCatalog",SALOME_ModuleCatalog.ModuleCatalog)

    # launch SalomeDS server, wait for it available in Naming Service
    SalomeDSServer().run()
    clt.waitNS("/Study")

    # launch 
    ConnectionManagerServer().run()

    # launch Session Server
    if options.gui:
        # process our list of extra args into a string redeable by session server (json style)
        pyscriptargs=""
        if options.extra_args: # pyscripts were specified, we transfer the info to gui
            pyscriptargs='--pyscript=%s' % json.dumps(options.extra_args)
        SessionServer().run(pyscriptargs) 

    # start launcher server
    LauncherServer().run()
    # clt.waitNS("/LauncherServer")

    if not options.gui:
        # in tui mode, start FactoryServer standalone
        # ContainerServer().run()  CNC KO?
        # run specified pyscripts, if any
        if options.extra_args:
            for file_args_dict in options.extra_args:
                for f in file_args_dict.keys():
                    command="python3 "+f
                    for arg in file_args_dict[f]:
                        command += " "+arg
                print ("command to execute pyscript: ", command)
                proc = subprocess.Popen(command, shell=True)
                #  addToKillList(proc.pid, command, args['port']) ??
                res = proc.wait()
                if res: sys.exit(1) # if there's an error when executing script, we should explicitly exit

    if options.gui:
        session=clt.waitNS("/Kernel/Session",SALOME.Session)
    return clt

def start_orb():
    # initialise orb and naming service
    searchFreePort()
    print("Initialise ORB and Naming Service")
    clt=orbmodule.client()
    return clt

def generate_module_catalog():
    salome_modules=os.getenv("SALOME_MODULES")
    assert salome_modules != None, "SALOME_MODULES variable not found!"
    cata_path=[]
    for module in salome_modules.split(","):
        module_root_dir = os.getenv(module + "_ROOT_DIR")
        module_cata = module + "Catalog.xml"
        cata_path.extend(glob.glob(os.path.join(module_root_dir,"share","salome",
                                                "resources",module.lower(), module_cata)))
    return ':'.join(cata_path)

# base class to start corba servers
class Server:
    CMD=[]
    def run(self):
        args = self.CMD
        pid = os.spawnvp(os.P_NOWAIT, args[0], args)
        print ("start server ", args, "  (pid = %s)" % pid)

class LauncherServer(Server):
   CMD=['SALOME_LauncherServer']

class ConnectionManagerServer(Server):
   CMD=['SALOME_ConnectionManagerServer']

class SalomeDSServer(Server):
   CMD=['SALOMEDS_Server']

class RegistryServer(Server):
   CMD=['SALOME_Registry_Server', '--salome_session','theSession']

class ContainerServer(Server):
   CMD=['SALOME_Container','FactoryServer','-ORBInitRef','NameService=corbaname::localhost']

class LoggerServer(Server):
   CMD=['SALOME_Logger_Server', 'logger.log']

class CatalogServer(Server):
   CMD=['SALOME_ModuleCatalog_Server','-common']
   def run(self):
       self.CMD = self.CMD + [generate_module_catalog()]
       Server.run(self)

class NotifyServer(Server):
   CMD=['notifd','-c','${KERNEL_ROOT_DIR}/share/salome/resources/channel.cfg -DFactoryIORFileName=/tmp/${LOGNAME}_rdifact.ior -DChannelIORFileName=/tmp/${LOGNAME}_rdichan.ior']

class SessionServer(Server):
   CMD=['SALOME_Session_Server','--with','Container','(','FactoryServer',')','--with', 'SalomeAppEngine', '(', ')', 'CPP', 'GUI', 'SPLASH', '--language=fr']
   def run(self, pyscriptopt):
       if pyscriptopt:  # communicate to gui the scripts to run
           self.CMD = self.CMD + [pyscriptopt] 
       salome_modules=os.getenv("SALOME_MODULES")
       assert salome_modules != None, "SALOME_MODULES variable not found!"
       self.CMD = self.CMD + ['--modules (' + salome_modules.replace(",",":") + ')' ]
       Server.run(self)

if __name__ == "__main__":
    main()
