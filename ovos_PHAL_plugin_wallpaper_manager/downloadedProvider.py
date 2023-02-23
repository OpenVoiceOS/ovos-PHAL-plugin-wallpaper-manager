# A downloaded wallpaper provider for the OVOS PHAL wallpaper manager plugin
# For wallpapers that are downloaded from the internet when using dynamic providers
# So users can select a previously downloaded wallpaper from a list as they will already have it
import os
from ovos_utils.log import LOG
from mycroft_bus_client.message import Message

class DownloadedProvider:
    def __init__(self, bus, local_path):
        self.id = "wm_downloaded_provider.openvoiceos"
        self.name = "Downloaded Wallpapers"
        self.bus = bus
        self.local_wallpaper_path = local_path
        self.wallpaper_collection = None
        self.provider_registered = False

        self.bus.on("ovos.wallpaper.manager.loaded",
                    self.collect_wallpapers)
        self.bus.on(f"{self.id}.get.wallpaper.collection",
                    self.supply_wallpaper_collection)

    def update_wallpaper_collection(self):
        self.collect_wallpapers()
        self.bus.emit(Message("ovos.wallpaper.manager.collect.collection.response", {
            "provider_name": self.id,
            "wallpaper_collection": self.wallpaper_collection
        }))

    def collect_wallpapers(self, message=None):
        for dirname, dirnames, filenames in os.walk(self.local_wallpaper_path):
            self.wallpaper_collection = filenames
            self.wallpaper_collection = [os.path.join(dirname, wallpaper) for wallpaper in self.wallpaper_collection]
            if not self.provider_registered:
                if len(self.wallpaper_collection) > 0:
                    LOG.info("Length of wallpaper collection is greater than 0, registering provider")
                    self.register_wallpaper_provider()

    def register_wallpaper_provider(self):
        LOG.info("Registering wallpaper provider")
        self.bus.emit(Message("ovos.wallpaper.manager.register.provider", {
            "provider_name": self.id,
            "provider_display_name": self.name
        }))
        self.provider_registered = True

    def supply_wallpaper_collection(self, message):
        self.collect_wallpapers()
        self.bus.emit(Message("ovos.wallpaper.manager.collect.collection.response", {
            "provider_name": self.id,
            "wallpaper_collection": self.wallpaper_collection
        }))