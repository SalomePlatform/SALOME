#! /usr/bin/env python3

################################################################
# WARNING: this file is automatically generated by SalomeTools #
# WARNING: and so could be overwritten at any time.            #
################################################################

import os
import sys
import subprocess

# Preliminary work to initialize path to SALOME Python modules
def __initialize():
  # define folder to store omniorb config (initially in virtual application folder)
  try:
    from salomeContextUtils import setOmniOrbUserPath
    setOmniOrbUserPath()
  except Exception as e:
    print(e)
    sys.exit(1)
# End of preliminary work

# salome doc only works for virtual applications. Therefore we overwrite it with this function
def _showDoc(modules):
    for module in modules:
      modulePath = os.getenv(module+"_ROOT_DIR")
      if modulePath != None:
        baseDir = os.path.join(modulePath, "share", "doc", "salome")
        docfile = os.path.join(baseDir, "gui", module.upper(), "index.html")
        if not os.path.isfile(docfile):
          docfile = os.path.join(baseDir, "tui", module.upper(), "index.html")
        if not os.path.isfile(docfile):
          docfile = os.path.join(baseDir, "dev", module.upper(), "index.html")
        if os.path.isfile(docfile):
          out, err = subprocess.Popen(["xdg-open", docfile]).communicate()
        else:
          print("Online documentation is not accessible for module:", module)
      else:
        print(module+"_ROOT_DIR not found!")

def main(args):
  # Identify application path then locate configuration files
  __initialize()

  if args == ['--help']:
    from salomeContext import usage
    usage()
    sys.exit(0)

  # Create a SalomeContext
  try:
    from salomeContext import SalomeContext, SalomeContextException
    context = SalomeContext(None)

    # Logger level error
    context.getLogger().setLevel(40)

    if len(args) >1 and args[0]=='doc':
        _showDoc(args[1:])
        return

    # Start SALOME, parsing command line arguments
    out, err, status = context.runSalome(args)
    sys.exit(status)

  except SalomeContextException as e:
    import logging
    logging.getLogger("salome").error(e)
    sys.exit(1)
 

if __name__ == "__main__":
  args = sys.argv[1:]
  main(args)
#