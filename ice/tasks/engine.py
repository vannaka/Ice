"""
IceEngine

The job of this class is to perform the functionality that Ice is defined by.
By that I mean the high level goal of `Adding ROMs to Steam`.
"""

import os

from pysteam import paths as steam_paths
from pysteam import shortcuts
from pysteam import steam as steam_module

from ice import backups
from ice import configuration
from ice import consoles
from ice import emulators
from ice import paths
from ice import settings
from ice.error.env_checker_error import EnvCheckerError
from ice.environment_checker import EnvironmentChecker
from ice.logs import logger
from ice.parsing.rom_parser import ROMParser
from ice.persistence.config_file_backing_store import ConfigFileBackingStore
from ice.rom_finder import ROMFinder

STEAM_CHECK_SKIPPED_WARNING = """\
Not checking whether Steam is running. Any changes made may be overwritten \
when Steam exits.\
"""

class TaskEngine(object):

  def __init__(
    self,
    steam,
    filesystem,
    app_settings):
    """Valid options for creating an IceEngine are as follows:

    * config    - The path to the config file to use. Searches the default paths
                  for 'config.txt' otherwise
    * consoles  - The path to the consoles file to use. Searches the default
                  paths for 'consoles.txt' if none is provided
    * emulators - The path to the emulators file to use. Searches the default
                  paths for 'emulators.txt' if none is provided
    """
    self.steam = steam
    self.filesystem = filesystem

    # We want to ignore the anonymous context, cause theres no reason to sync
    # ROMs for it since you cant log in as said user.
    is_user_context = lambda context: context.user_id != 'anonymous'
    self.users = filter(is_user_context, steam_module.local_user_contexts(self.steam))

    logger.debug("Initializing Ice")

    self.app_settings = app_settings

    parser = ROMParser()
    self.rom_finder = ROMFinder(app_settings.config, filesystem, parser)

  def validate_environment(self, skip_steam_check):
    """
    Validate that the current environment meets all of Ice's requirements.
    """
    with EnvironmentChecker(self.filesystem) as env_checker:
      if not skip_steam_check:
        # If Steam is running then any changes we make will be overwritten
        env_checker.require_program_not_running("Steam")
      else:
        logger.warning(STEAM_CHECK_SKIPPED_WARNING)
      # I'm not sure if there are situations where this won't exist, but I
      # assume that it does everywhere and better safe than sorry
      env_checker.require_directory_exists(self.steam.userdata_directory)
      # This is used to store history information and such
      env_checker.require_directory_exists(paths.application_data_directory())

      for console in self.app_settings.consoles:
        # Consoles assume they have a ROMs directory
        env_checker.require_directory_exists(consoles.console_roms_directory(self.app_settings.config, console))

      for user in self.users:
        # If the user hasn't added any grid images on their own then this
        # directory wont exist, so we require it explicitly here
        env_checker.require_directory_exists(steam_paths.custom_images_directory(user))
        # And it needs to be writable if we are going to save images there
        env_checker.require_writable_path(steam_paths.custom_images_directory(user))

  def run(
    self,
    tasks,
    skip_steam_check=False,
    dry_run=False):
    if self.steam is None:
      logger.error("Cannot run Ice because Steam doesn't appear to be installed")
      return

    logger.info("=========== Starting Ice ===========")
    try:
      self.validate_environment(skip_steam_check)
    except EnvCheckerError as e:
      logger.info("Ice cannot run because of issues with your system.\n")
      logger.info("* %s" % e.message)
      logger.info("\nPlease resolve these issues and try running Ice again")
      return

    # TODO: Create any missing directories that Ice will need
    log_emulators(self.app_settings.emulators)
    log_consoles(self.app_settings.consoles)

    roms = self.rom_finder.roms_for_consoles(self.app_settings.consoles)

    [ task(self.users, roms, dry_run=dry_run) for task in tasks ]

# Logging methods. The purpose of these methods isn't so much to log things as
# they are to inform the user of the state of their setup (as Ice sees it).
# They were originally on ice_logging but since they require knowledge of
# emulators/consoles/configurations it meant that I couldn't log from a bunch
# of different files. Clearly not ideal, and they weren't exactly a great fit
# on the logger class anyway
#
# TODO(scottrice): Find a better home for these functions

def log_emulators(emulators):
  for emulator in emulators:
    logger.info("Detected Emulator: %s" % emulator.name)

def log_consoles(consoles):
  for console in consoles:
    logger.info("Detected Console: %s => %s" % (console.fullname, console.emulator.name))
