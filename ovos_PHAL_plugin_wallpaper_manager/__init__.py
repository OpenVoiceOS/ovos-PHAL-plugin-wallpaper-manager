import os
import threading
import requests
import hashlib
from mycroft_bus_client.message import Message
from ovos_plugin_manager.phal import PHALPlugin
from ovos_utils.log import LOG
from ovos_utils.skills.settings import PrivateSettings
from ovos_utils.xdg_utils import xdg_data_home
from ovos_config.config import Configuration
from ovos_utils.events import EventSchedulerInterface
from wallpaper_changer import set_wallpaper
from ovos_PHAL_plugin_wallpaper_manager.downloadedProvider import DownloadedProvider

class WallpaperManager(PHALPlugin):

    def __init__(self, bus=None, config=None):
        name = "ovos-PHAL-plugin-wallpaper-manager"
        super().__init__(bus=bus, name=name, config=config)

        # this is a XDG compliant json storage object similar to self.settings in MycroftSkill
        # it can be used to keep state
        core_config = Configuration()
        enclosure_config = core_config.get("gui") or {}
        self.active_extension = enclosure_config.get("extension", "generic")
        self.event_scheduler_interface = EventSchedulerInterface(name=name, bus=self.bus)

        self.settings = PrivateSettings(name)
        self.registered_providers = []
        self.setup_default_provider_running = False
        self.threading_event = threading.Event()
        self.local_wallpaper_storage = os.path.join(xdg_data_home(), "wallpapers")
    
        if not os.path.exists(self.local_wallpaper_storage):
            os.makedirs(self.local_wallpaper_storage)
        self.d_provider = DownloadedProvider(self.bus,
                                             self.local_wallpaper_storage)

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
        
        # Handle swipe and voice intents to change wallpaper, also auto rotation
        self.bus.on("ovos.wallpaper.manager.change.wallpaper", self.handle_change_wallpaper)

        # Auto wallpaper rotation and setting up time for change
        self.bus.on("ovos.wallpaper.manager.enable.auto.rotation", self.handle_enable_auto_rotation)
        self.bus.on("ovos.wallpaper.manager.disable.auto.rotation", self.handle_disable_auto_rotation)
        self.bus.on("ovos.wallpaper.manager.get.auto.rotation", self.handle_get_auto_rotation)
        
        
        # Providers Configuration API to be used By Settings UI
        # Some wallpaper providers might want to show configuration options to the user
        self.bus.on("ovos.wallpaper.manager.get.provider.config", self.handle_get_provider_config)
        self.bus.on("ovos.wallpaper.manager.set.provider.config", self.handle_set_provider_config)
        self.bus.on("ovos.wallpaper.manager.provider.config", self.handle_received_provider_config)
        
        # We cannot guarantee when this plugin will be loaded so emit a message to any providers
        # that are waiting for the plugin to be loaded so they can immediately register
        self.bus.emit(Message("ovos.wallpaper.manager.loaded"))

    @property
    def selected_provider(self):
        return self.settings.get("selected_provider", "")

    @selected_provider.setter
    def selected_provider(self, val):
        self.settings["selected_provider"] = str(val)
        self.settings.store()

    @property
    def selected_wallpaper(self):
        return self.settings.get("selected_wallpaper", "")

    @selected_wallpaper.setter
    def selected_wallpaper(self, val):
        self.settings["selected_wallpaper"] = str(val)
        self.settings.store()

    @property
    def wallpaper_rotation(self):
        return self.settings.get("wallpaper_rotation", True)

    @wallpaper_rotation.setter
    def wallpaper_rotation(self, val):
        self.settings["wallpaper_rotation"] = bool(val)
        self.settings.store()

    @property
    def wallpaper_rotation_time(self):
        return self.settings.get("wallpaper_rotation_time", 30)

    @wallpaper_rotation_time.setter
    def wallpaper_rotation_time(self, val):
        self.settings["wallpaper_rotation_time"] = int(val)
        self.settings.store()

    def handle_register_provider(self, message):
        # Required will be used internally as the id, should be generally the skill id
        provider_name = message.data.get("provider_name", "")
        # Required will be used for QML display "Astronomy Skill"
        provider_display_name = message.data.get("provider_display_name", "")
        provider_configurable = message.data.get("provider_configurable", False)

        if not provider_name or not provider_display_name:
            LOG.error("Unable to register wallpaper provider, missing required parameters")

        if not any((provider.get('provider_name') == provider_name
                    for provider in self.registered_providers)):
            self.registered_providers.append({
                "provider_name": provider_name,
                "provider_display_name": provider_display_name,
                "provider_configurable": provider_configurable,
                "wallpaper_collection": [],
                "default_wallpaper": "",
                "previous_wallpaper": "",
            })
            self.bus.emit(Message("ovos.phal.wallpaper.manager.provider.registered"))

        self.collect_wallpapers_from_provider(Message("ovos.phal.wallpaper.manager.provider.collection.updated", 
                                                        {"provider_name": provider_name}))

    def handle_get_registered_providers(self, message):
        self.bus.emit(message.response(data={"registered_providers": self.registered_providers}))

    def handle_set_active_provider(self, message):
        provider_name = message.data.get("provider_name")
        provider_image = message.data.get("provider_image", "")
        for provider in self.registered_providers:
            if provider.get("provider_name") == self.selected_provider:
                provider["previous_wallpaper"] = self.selected_wallpaper
                break

        self.selected_provider = provider_name
        self.selected_wallpaper = ""

        wallpaper_collection = None
        default_wallpaper = None
        previous_wallpaper = None
        for provider in self.registered_providers:
            if provider.get("provider_name") == self.selected_provider:
                wallpaper_collection = provider.get("wallpaper_collection")
                default_wallpaper = provider.get("default_wallpaper")
                previous_wallpaper = provider.get("previous_wallpaper")
                break
        
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

        wallpaper_collection = None
        for provider in self.registered_providers:
            if provider.get("provider_name") == self.selected_provider:
                wallpaper_collection = provider.get("wallpaper_collection")
                break

        if wallpaper_collection:
            if self.selected_wallpaper:
                wallpaper_path = next((wp for wp in wallpaper_collection if wp.endswith(self.selected_wallpaper)), None)
            else:
                default_wallpaper_name = message.data.get("default_wallpaper_name", "default.jpg")                
                default_wallpaper = next((wp for wp in wallpaper_collection if wp.endswith(default_wallpaper_name)), None)
                if default_wallpaper:
                    for provider in self.registered_providers:
                        if provider.get("provider_name") == self.selected_provider:
                            provider["default_wallpaper"] = default_wallpaper
                            break
                wallpaper_path = default_wallpaper

            if wallpaper_path:
                self.selected_wallpaper = wallpaper_path

        if not wallpaper_collection:
            self.bus.emit(Message(f"{self.selected_provider}.get.new.wallpaper"))
            self.threading_event.wait()

        self.bus.emit(message.response(data={"provider_name": self.selected_provider, "url": self.selected_wallpaper}))
        self.setup_default_provider_running = False

    def collect_wallpapers_from_provider(self, message):
        provider_name = message.data.get("provider_name")
        self.bus.emit(Message(f"{provider_name}.get.wallpaper.collection"))

    def handle_wallpaper_collection(self, message):
        provider_name = message.data.get("provider_name")
        wallpaper_collection = message.data.get("wallpaper_collection")
        if provider_name and wallpaper_collection:
            for provider in self.registered_providers:
                if provider.get("provider_name") == provider_name:
                    provider["wallpaper_collection"] = wallpaper_collection
    
    def get_wallpaper_collection_from_provider(self, message):
        provider_name = message.data.get("provider_name")
        if provider_name:
            for provider in self.registered_providers:
                if provider.get("provider_name") == provider_name:
                    self.bus.emit(message.response(
                        data={"provider_name": provider_name,
                              "wallpaper_collection": provider["wallpaper_collection"]}))
    
    def get_wallpaper_collection(self, message):
        current_wallpaper_collection = []
        for provider in self.registered_providers:
            if provider.get("provider_name") == self.selected_provider:
                current_wallpaper_collection = provider["wallpaper_collection"]

        self.bus.emit(message.response(
            data={"wallpaper_collection": current_wallpaper_collection}))

    def handle_set_wallpaper(self, message):
        wallpaper = message.data.get("url")
        if not wallpaper:
            LOG.error("No wallpaper provided by the provider")

        if wallpaper.startswith("http") or wallpaper.startswith("https"):
            wallpaper = self.store_wallpaper_to_local(wallpaper)

        if not self.setup_default_provider_running:
            if self.active_extension == "smartspeaker" or self.active_extension == "mobile":
                self.bus.emit(Message("homescreen.wallpaper.set", {"url": wallpaper}))
            else:
                set_wallpaper(wallpaper)
                
            self.selected_wallpaper = wallpaper
        else:
            self.selected_wallpaper = wallpaper
            self.threading_event.set()

    def handle_get_wallpaper(self, message):
        self.bus.emit(message.response(data={"url": self.selected_wallpaper}))
        
    def get_wallpaper_idx(self, collection, filename):
        try:
            index_element = collection.index(filename)
            return index_element
        except ValueError:
            return None
        
    def handle_change_wallpaper(self, message=None):
        wallpaper_collection = []
        for provider in self.registered_providers:
            if provider.get("provider_name") == self.selected_provider:
                wallpaper_collection = provider["wallpaper_collection"]
            
        if len(wallpaper_collection) > 0:
            current_idx = self.get_wallpaper_idx(wallpaper_collection, self.selected_wallpaper)
            collection_length = len(wallpaper_collection) - 1
            if not current_idx == collection_length:
                future_idx = current_idx + 1
                self.handle_set_wallpaper(Message("ovos.wallpaper.manager.set.wallpaper", 
                                                  {"url": wallpaper_collection[future_idx]}))
            else:
                self.handle_set_wallpaper(Message("ovos.wallpaper.manager.set.wallpaper", 
                                                  {"url": wallpaper_collection[0]}))
            
        else:
            self.bus.emit(Message(f"{self.selected_provider}.get.new.wallpaper"))
            
    def handle_enable_auto_rotation(self, message):
        rotation_time = message.data.get("rotation_time")
        if rotation_time:
            self.wallpaper_rotation_time = rotation_time
        else:
            self.wallpaper_rotation_time = 30
        
        self.event_scheduler_interface.schedule_event(
            self.handle_change_wallpaper, self.wallpaper_rotation_time, data=None, name="wallpaper_rotation"
        )
        self.wallpaper_rotation = True
        self.bus.emit(Message("ovos.wallpaper.manager.auto.rotation.enabled"))
    
    def handle_disable_auto_rotation(self, message):
        self.event_scheduler_interface.cancel_scheduled_event("wallpaper_rotation")
        self.wallpaper_rotation = False
        self.bus.emit(Message("ovos.wallpaper.manager.auto.rotation.disabled"))
        
    def handle_get_auto_rotation(self, message):
        self.bus.emit(message.response(data={"auto_rotation": self.wallpaper_rotation,
                                             "rotation_time": self.wallpaper_rotation_time}))
        
    def handle_get_provider_config(self, message):
        provider_name = message.data.get("provider_name")
        for provider in self.registered_providers:
            if provider.get("provider_name") == provider_name:
                if provider.get("provider_configurable"):
                    self.bus.emit(Message(f"{provider_name}.get.wallpaper.config"))
    
    def handle_received_provider_config(self, message):
        provider_name = message.data.get("provider_name")
        config = message.data.get("config")
        self.bus.emit(Message("ovos.wallpaper.manager.get.provider.config.response",
                              data={"provider_name": provider_name, "config": config}))
    
    def handle_set_provider_config(self, message):
        provider_name = message.data.get("provider_name")
        config = message.data.get("config")
        self.bus.emit(Message(f"{provider_name}.set.wallpaper.config", {"config": config}))
        
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
                open(wallpaper_path, "wb").write(wallpaper.content)
                self.d_provider.update_wallpaper_collection()
                return wallpaper_path
            except Exception as e:
                LOG.error(e)
                return None