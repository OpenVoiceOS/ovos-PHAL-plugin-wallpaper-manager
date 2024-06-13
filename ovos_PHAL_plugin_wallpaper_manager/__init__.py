import hashlib
import os
import requests

from os.path import isfile
from ovos_bus_client.message import Message
from ovos_config.config import update_mycroft_config
from ovos_plugin_manager.phal import PHALPlugin
from ovos_utils.events import EventSchedulerInterface
from ovos_utils.log import LOG
from ovos_utils.xdg_utils import xdg_data_home
from ovos_workshop.settings import PrivateSettings
from wallpaper_changer import set_wallpaper


class WallpaperManager(PHALPlugin):

    def __init__(self, bus=None, config=None):
        name = "ovos-PHAL-plugin-wallpaper-manager"
        super().__init__(bus=bus, name=name, config=config)
        self.event_scheduler_interface = EventSchedulerInterface(skill_id=name,
                                                                 bus=self.bus)

        settings = PrivateSettings(name)
        if isfile(settings.path):
            LOG.warning(f"Legacy config found at {settings.path}")
            for key, value in settings.items():
                self.config[key] = value
            os.remove(settings.path)
            new_config = {"PHAL": {self.name: self.config}}
            update_mycroft_config(config=new_config, bus=self.bus)

        self.registered_providers = {}
        self.setup_default_provider_running = False
        self.local_wallpaper_storage = os.path.join(xdg_data_home(),
                                                    "wallpapers")

        if not os.path.exists(self.local_wallpaper_storage):
            os.makedirs(self.local_wallpaper_storage)

        # Manage provider registration, activation and deactivation
        # Multiple clients can be registered, but only one can be active at a time
        self.bus.on("ovos.wallpaper.manager.register.provider",
                    self.handle_register_provider)
        self.bus.on("ovos.wallpaper.manager.get.registered.providers",
                    self.handle_get_registered_providers)
        self.bus.on("ovos.wallpaper.manager.set.active.provider",
                    self.handle_set_active_provider)
        self.bus.on("ovos.wallpaper.manager.get.active.provider",
                    self.handle_get_active_provider)

        # Private method to only be used by homescreen skills
        # This is used to set the default provider if none is selected
        # Wallpapers need to be available as soon as the homescreen is loaded
        self.bus.on("ovos.wallpaper.manager.setup.default.provider",
                    self.handle_setup_default_provider)

        # *Optional* Wallpaper collection if the provider wants to provide an updated collection
        # Homescreen for example provides a collection of local wallpapers that can be selected from
        # Providers that do not provide a collection will be expected to provide a wallpaper directly
        # on the following message "provider_name.get.new.wallpaper"
        self.bus.on("ovos.wallpaper.manager.collect.collection.response",
                    self.handle_wallpaper_collection)
        self.bus.on("ovos.wallpaper.manager.get.collection",
                    self.get_wallpaper_collection)
        self.bus.on("ovos.wallpaper.manager.get.collection.from.provider",
                    self.get_wallpaper_collection_from_provider)
        self.bus.on("ovos.wallpaper.manager.update.collection",
                    self.collect_wallpapers_from_provider)

        # Manage when the provider wants to set a wallpaper / user wants to set a wallpaper
        # both simply call the same method
        self.bus.on("ovos.wallpaper.manager.set.wallpaper",
                    self.handle_set_wallpaper)
        self.bus.on("ovos.wallpaper.manager.get.wallpaper",
                    self.handle_get_wallpaper)

        # Handle swipe and voice intents to change wallpaper, also auto-rotation
        self.bus.on("ovos.wallpaper.manager.change.wallpaper",
                    self.handle_change_wallpaper)

        # Auto wallpaper rotation and setting up time for change
        self.bus.on("ovos.wallpaper.manager.enable.auto.rotation",
                    self.handle_enable_auto_rotation)
        self.bus.on("ovos.wallpaper.manager.disable.auto.rotation",
                    self.handle_disable_auto_rotation)
        self.bus.on("ovos.wallpaper.manager.get.auto.rotation",
                    self.handle_get_auto_rotation)

        if self.wallpaper_rotation:
            # Start rotation if configured
            self._start_auto_rotation()

        # We cannot guarantee when this plugin will be loaded, so emit a message
        # to any providers that are waiting for the plugin to be loaded, so they
        # can immediately register
        self.bus.emit(Message("ovos.wallpaper.manager.loaded"))

    @property
    def selected_provider(self) -> str:
        """
        Get the selected wallpaper provider ID from configuration
        """
        return self.config.get("selected_provider") or ""

    @selected_provider.setter
    def selected_provider(self, val: str):
        """
        Set the wallpaper provider ID
        """
        self.config["selected_provider"] = val
        new_config = {"PHAL": {self.name: self.config}}
        update_mycroft_config(config=new_config, bus=self.bus)

    @property
    def selected_wallpaper(self) -> str:
        """
        Get the currently selected wallpaper URI
        """
        return self.config.get("selected_wallpaper") or ""

    @selected_wallpaper.setter
    def selected_wallpaper(self, val: str):
        """
        Set the currently selected wallpaper URI
        """
        self.config["selected_wallpaper"] = val
        new_config = {"PHAL": {self.name: self.config}}
        update_mycroft_config(config=new_config, bus=self.bus)

    @property
    def wallpaper_rotation(self) -> bool:
        """
        If true, rotate through all wallpapers from the selected provider
        """
        return self.config.get("wallpaper_rotation") or False

    @wallpaper_rotation.setter
    def wallpaper_rotation(self, val: bool):
        """
        Enable rotating through all wallpapers from the selected provider
        """
        self.config["wallpaper_rotation"] = bool(val)
        new_config = {"PHAL": {self.name: self.config}}
        update_mycroft_config(config=new_config, bus=self.bus)

    @property
    def wallpaper_rotation_time(self) -> int:
        """
        Get the time in seconds to display each wallpaper from the selected
        provider
        """
        try:
            rot_time = self.config.get("wallpaper_rotation_time") or 30
            return int(rot_time)
        except Exception as e:
            LOG.error(e)
            return 30

    @wallpaper_rotation_time.setter
    def wallpaper_rotation_time(self, val: int):
        """
        Set the time in seconds to display each wallpaper from the selected
        provider
        """
        self.config["wallpaper_rotation_time"] = int(val)
        new_config = {"PHAL": {self.name: self.config}}
        update_mycroft_config(config=new_config, bus=self.bus)

    def handle_register_provider(self, message):
        # Required will be used internally as the id, should be generally the skill id
        provider_name = message.data.get("provider_name", "")
        # Required will be used for QML display "Astronomy Skill"
        provider_display_name = message.data.get("provider_display_name", "")
        provider_configurable = message.data.get("provider_configurable", False)

        if not provider_name or not provider_display_name:
            LOG.error("Unable to register wallpaper provider, missing required parameters")
        if provider_name not in self.registered_providers:
            self.registered_providers[provider_name] = {
                "provider_name": provider_name,
                "provider_display_name": provider_display_name,
                "provider_configurable": provider_configurable,
                "wallpaper_collection": [],
                "default_wallpaper": "",
                "previous_wallpaper": "",
            }
            self.bus.emit(Message("ovos.phal.wallpaper.manager.provider.registered"))

        self.collect_wallpapers_from_provider(Message("ovos.phal.wallpaper.manager.provider.collection.updated",
                                                      {"provider_name": provider_name}))

    def handle_get_registered_providers(self, message):
        self.bus.emit(message.response(data={"registered_providers": list(self.registered_providers.values())}))

    def handle_set_active_provider(self, message):
        provider_name = message.data.get("provider_name")
        provider_image = message.data.get("provider_image", "")
        if provider_name in self.registered_providers:
            self.registered_providers[provider_name]["previous_wallpaper"] = \
                self.selected_wallpaper

        self.selected_provider = provider_name
        self.selected_wallpaper = ""

        provider_data = self.registered_providers.get(self.selected_provider)
        wallpaper_collection = provider_data.get("wallpaper_collection")
        default_wallpaper = provider_data.get("default_wallpaper")
        previous_wallpaper = provider_data.get("previous_wallpaper")

        if not self.selected_wallpaper and provider_image:
            self.handle_set_wallpaper(Message("ovos.phal.wallpaper.manager.set.wallpaper",
                                              {"url": provider_image}))
        elif not self.selected_wallpaper and previous_wallpaper:
            self.handle_set_wallpaper(Message("ovos.phal.wallpaper.manager.set.wallpaper",
                                              {"url": previous_wallpaper}))
        elif not self.selected_wallpaper and default_wallpaper:
            self.handle_set_wallpaper(Message("ovos.phal.wallpaper.manager.set.wallpaper",
                                              {"url": default_wallpaper}))
        elif not self.selected_wallpaper and wallpaper_collection:
            self.handle_set_wallpaper(Message("ovos.phal.wallpaper.manager.set.wallpaper",
                                              {"url": wallpaper_collection[0]}))
        elif not self.selected_wallpaper and not wallpaper_collection:
            self.bus.emit(Message(f"{self.selected_provider}.get.new.wallpaper"))

    def handle_get_active_provider(self, message):
        self.bus.emit(message.response(data={"active_provider": self.selected_provider}))

    def handle_setup_default_provider(self, message):
        self.setup_default_provider_running = True
        provider_name = message.data.get("provider_name")

        if not self.selected_provider:
            self.selected_provider = provider_name

        wallpaper_collection = self.registered_providers.get(self.selected_provider, {}).get("wallpaper_collection")

        if wallpaper_collection:
            if self.selected_wallpaper:
                wallpaper_path = next((wp for wp in wallpaper_collection if wp.endswith(self.selected_wallpaper)), None)
            else:
                default_wallpaper_name = message.data.get("default_wallpaper_name", "default.jpg")
                default_wallpaper = next((wp for wp in wallpaper_collection if wp.endswith(default_wallpaper_name)),
                                         None)
                if default_wallpaper:
                    self.registered_providers.get(self.selected_provider,
                                                  {})["default_wallpaper"] = \
                        default_wallpaper

                wallpaper_path = default_wallpaper

            if wallpaper_path:
                self.selected_wallpaper = wallpaper_path

        if not wallpaper_collection:
            self.bus.wait_for_response(
                message.forward(f"{self.selected_provider}.get.new.wallpaper"),
                timeout=60)

        self.bus.emit(message.response(
            data={"provider_name": self.selected_provider,
                  "url": self.selected_wallpaper}))
        self.setup_default_provider_running = False

    def collect_wallpapers_from_provider(self, message):
        provider_name = message.data.get("provider_name")
        self.bus.emit(Message(f"{provider_name}.get.wallpaper.collection"))

    def handle_wallpaper_collection(self, message):
        provider_name = message.data.get("provider_name")
        wallpaper_collection = message.data.get("wallpaper_collection")
        if provider_name and wallpaper_collection and provider_name in self.registered_providers:
            self.registered_providers[provider_name]["wallpaper_collection"] = wallpaper_collection

    def get_wallpaper_collection_from_provider(self, message):
        provider_name = message.data.get("provider_name")
        if provider_name:
            provider = self.registered_providers.get(provider_name)
            if provider:
                self.bus.emit(message.response(
                    data={"provider_name": provider_name,
                          "wallpaper_collection": provider["wallpaper_collection"]}))

    def get_wallpaper_collection(self, message):
        current_wallpaper_collection = self.registered_providers.get(self.selected_provider, {}).get("wallpaper_collection") or list()
        self.bus.emit(message.response(
            data={"wallpaper_collection": current_wallpaper_collection}))

    def handle_set_wallpaper(self, message):
        wallpaper = message.data.get("url")
        if not wallpaper:
            LOG.error("No wallpaper provided by the provider")

        if wallpaper.startswith("http") or wallpaper.startswith("https"):
            wallpaper = self.store_wallpaper_to_local(wallpaper)

        if not self.setup_default_provider_running:
            # change homescreen wallpaper
            self.bus.emit(Message("homescreen.wallpaper.set", {"url": wallpaper}))

            # if running on a desktop, also change it's wallpaper
            # TODO - config flag?
            try:
                set_wallpaper(wallpaper)
            except:
                # https://github.com/OpenVoiceOS/ovos-PHAL-plugin-wallpaper-manager/issues/7
                pass  # TODO - happens in EGLFS, fix later

            self.selected_wallpaper = wallpaper
        else:
            self.selected_wallpaper = wallpaper
        self.bus.emit(message.response({"wallpaper": wallpaper}))

    def handle_get_wallpaper(self, message):
        self.bus.emit(message.response(data={"url": self.selected_wallpaper}))

    def get_wallpaper_idx(self, collection, filename):
        try:
            index_element = collection.index(filename)
            return index_element
        except ValueError:
            return None

    def handle_change_wallpaper(self, message: Message):
        """
        Handle a request to change the wallpaper to the next item in the
        active collection.
        @param message: `ovos.wallpaper.manager.change.wallpaper` message or
            message from EventScheduler
        """
        wallpaper_collection = self.registered_providers.get(
            self.selected_provider, {}).get("wallpaper_collection") or list()

        if len(wallpaper_collection) > 0:
            current_idx = self.get_wallpaper_idx(wallpaper_collection,
                                                 self.selected_wallpaper)
            final_idx = len(wallpaper_collection) - 1
            LOG.debug(f"Getting new wallpaper. current={current_idx} "
                      f"final_idx={final_idx}")
            if not current_idx == final_idx:
                future_idx = current_idx + 1
                self.handle_set_wallpaper(
                    message.forward("ovos.wallpaper.manager.set.wallpaper",
                                    {"url": wallpaper_collection[future_idx]}))
            else:
                self.handle_set_wallpaper(
                    message.forward("ovos.wallpaper.manager.set.wallpaper",
                                    {"url": wallpaper_collection[0]}))

        else:
            LOG.info("No wallpaper in registered providers")
            self.bus.emit(message.forward(f"{self.selected_provider}.get.new.wallpaper"))

    def _start_auto_rotation(self):
        """
        Start rotating through wallpapers. This setting will persist through
        module/plugin reloads.
        """
        LOG.info("Starting wallpaper rotation")
        self.event_scheduler_interface.schedule_repeating_event(
            self.handle_change_wallpaper, None, self.wallpaper_rotation_time,
            data=None, name="wallpaper_rotation")
        self.wallpaper_rotation = True
        self.bus.emit(Message("ovos.wallpaper.manager.auto.rotation.enabled"))

    def handle_enable_auto_rotation(self, message):
        self.wallpaper_rotation_time = message.data.get("rotation_time") or \
                                       self.wallpaper_rotation_time
        self._start_auto_rotation()

    def handle_disable_auto_rotation(self, message):
        LOG.info("Stopping wallpaper rotation")
        self.event_scheduler_interface.cancel_scheduled_event("wallpaper_rotation")
        self.wallpaper_rotation = False
        self.bus.emit(Message("ovos.wallpaper.manager.auto.rotation.disabled"))

    def handle_get_auto_rotation(self, message):
        self.bus.emit(message.response(data={"auto_rotation": self.wallpaper_rotation,
                                             "rotation_time": self.wallpaper_rotation_time}))

    def store_wallpaper_to_local(self, url):
        wallpaper_name = url.split("/")[-1]
        valid_extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp"]
        if not any(ext in wallpaper_name for ext in valid_extensions):
            wallpaper_url_hash = hashlib.md5(url.encode()).hexdigest()
            wallpaper_name = f"wallpaper-{wallpaper_url_hash}.jpg"

        wallpaper_path = os.path.join(self.local_wallpaper_storage, wallpaper_name)
        if os.path.exists(wallpaper_path):
            return wallpaper_path
        else:
            try:
                wallpaper = requests.get(url, allow_redirects=True)
                with open(wallpaper_path, "wb") as f:
                    f.write(wallpaper.content)
                return wallpaper_path
            except Exception as e:
                LOG.error(e)
                return None
