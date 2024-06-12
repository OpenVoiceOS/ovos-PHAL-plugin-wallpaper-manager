# OVOS PHAL PLUGIN WALLPAPER MANAGER
This PHAL plugin provides a central wallpaper management interface for homescreens and other desktops

### What is the Wallpaper Management Interface ?
The wallpaper management interface provides functionality for providing a central interface for homescreen and desktop wallpaper management, this interface is responsible for providing a list of available wallpapers and also provides functionality for setting a wallpaper from the list of available wallpapers. This interface supports different types of wallpaper providers, this can be a local provider that provides wallpapers from the local filesystem or a remote provider that provides wallpapers from a remote url. 

### Supported Desktop Environments

- **ovos-shell** (via [homescreen skill](https://github.com/OpenVoiceOS/skill-ovos-homescreen))
- **GNOME**: `gnome`, `unity`, `cinnamon`
- **MATE**: `mate`
- **XFCE**: `xfce4`
- **KDE**: `kde`
- **LXDE**: `lxde`
- **Fluxbox**: `fluxbox`
- **Openbox**: `openbox`
- **IceWM**: `icewm`
- **JWM**: `jwm`
- **AfterStep**: `afterstep`
- **Blackbox**: `blackbox`
- **WindowMaker**: `windowmaker`

Platform support provided by https://github.com/OpenVoiceOS/wallpaper_changer

### Install
`pip install ovos-PHAL-plugin-wallpaper-manager`

## Event & API Details and Usage:

### Registration / Activation of Wallpaper Providers API
Wallpaper providers are required to register themselves with the central wallpaper management interface, this is done by sending the following event:

``` python
    # ovos.wallpaper.manager.register.provider
    # type: Request
    # description: Register a wallpaper provider to the plugin
    # data required:
        # provider_name = typically the self.skill_id of the skill that provides the wallpaper provider
        # provider_display_name = A display name for the wallpaper provider, that will be displayed on the selection screens
        # (optional) provider_configurable = True if the wallpaper provider is configurable, False if not
```

On successful registration of a wallpaper provider, the wallpaper management interface will respond with the following event:
``` python
    # ovos.phal.wallpaper.manager.provider.registered
    # type: Response
    # description: Registration successful
```

Activate a wallpaper provider by sending the following event:


``` python
    # ovos.wallpaper.manager.set.active.provider
    # type: Request
    # description: Activate a wallpaper provider
    # data required:
        # provider_name = typically the self.skill_id of the skill that is the wallpaper provider
```

Note: This is handled by the Wallpapers Settings UI on "smartspeaker" and "mobile" GUI platforms,
Skills / Wallpaper providers must not be sending this unless they want to force override the currently set provider.

### Wallpaper Collection API
A wallpaper provider can send a collection of wallpapers to the wallpaper management interface, this is optional and will depend on case by case basis, where some providers might have their own collection of wallpapers and some 
might not and depend on an online source for wallpapers.

After registration of a wallpaper provider, the wallpaper management interface will send an event to the wallpaper provider to request a collection of wallpapers, Any provider wanting to provide wallpapers can do so by listening for the following signal:

``` python
    # {provider_name}.get.wallpaper.collection
    # type: Request
    # description: Request a collection of wallpapers from the wallpaper provider
```

and responding to the above signal by sending the following event:

``` python
    # ovos.wallpaper.manager.collect.collection.response
    # type: Response
    # description: Response to the wallpaper collection request
    # data required:
        # provider_name = typically the self.skill_id of the skill that provides the wallpaper provider
        # wallpaper_collection = a list of full wallpaper paths that are available from the wallpaper provider
```

the wallpaper provider can also ask the wallpaper management interface to update its wallpaper collection by sending the following event at any time:

``` python
    # ovos.wallpaper.manager.update.collection
    # type: Request
    # description: Request the wallpaper management interface to update its wallpaper collection
    # data required:
        # provider_name = typically the self.skill_id of the skill that provides the wallpaper provider
```

### Wallpaper Request For Non Collection Providers API
If a wallpaper provider does not provide a collection of wallpapers, the wallpaper management interface will always send an event to the wallpaper provider to request for a new wallpaper, The wallpaper provider must listen for the following signal:

``` python
    # {provider_name}.get.new.wallpaper
    # type: Request
    # description: Request a new wallpaper from the wallpaper provider
```

The wallpaper provider must respond to the above signal by sending the following event:

``` python
    # ovos.wallpaper.manager.set.wallpaper
    # type: Response
    # description: Response to the wallpaper request to set new wallpaper
    # data required:
        # url = the full path of the wallpaper that is to be set
```

### Get and Set Wallpaper API
The wallpaper management interface provides functionality for getting and setting wallpapers, the wallpaper management interface will send the following event to get the current wallpaper:

``` python
    # ovos.wallpaper.manager.get.wallpaper
    # type: Request
    # description: Request the wallpaper management interface to get the current wallpaper
```

The wallpaper management interface will respond to the above event with the following event:

``` python
    # ovos.wallpaper.manager.get.wallpaper.response
    # type: Response
    # description: Response to the wallpaper request to get the current wallpaper
    # data sent:
        # url = the full path of the current wallpaper
```

To set a wallpaper, the wallpaper management interface can be sent the following event:

``` python
    # ovos.wallpaper.manager.set.wallpaper
    # type: Request
    # description: Request the wallpaper management interface to set a new wallpaper
    # data required:
        # url = the full path of the wallpaper that is to be set
```

Note: 
- For platforms where homescreens are supported the above event will cause the wallpaper management interface will set the homescreen wallpaper.
- For non homescreen platforms like the desktop, the above event will cause the wallpaper management interface to set the desktop wallpaper.


### Change Wallpapers API
Any skill / event can request the wallpaper management interface to change the wallpaper by sending the following event:

``` python
    # ovos.wallpaper.manager.change.wallpaper
    # type: Request
    # description: Request the wallpaper management interface to change the wallpaper
```

Note: 
- If the selected provider provides a collection of wallpapers, the wallpaper management interface will select the next wallpaper from the collection and set it as the wallpaper.
- If the selected provider does not provide a collection of wallpapers, the wallpaper management interface will send a request to the provider to get a new wallpaper.

### AutoRotate Wallpapers API
The wallpaper management interface provides functionality for automatically rotating wallpapers, this is done by sending the following event:

``` python
    # ovos.wallpaper.manager.enable.auto.rotation
    # type: Request
    # description: Request the wallpaper management interface to enable auto rotate and set an wallpaper rotation interval
    # data required:
        # rotation_time = the time in seconds at which the wallpapers should be rotated
```

Wallpaper auto rotation can be disabled by sending the following event:

``` python
    # ovos.wallpaper.manager.disable.auto.rotation
    # type: Request
    # description: Request the wallpaper management interface to disable auto rotate
```

## Example Implementation in a Wallpaper Provider Skill Providing a Collection of Wallpapers:

``` python

def ExampleWallpaperProvider(OVOSSkill):
    def initialize(self):
        self.add_event("ovos.wallpaper.manager.loaded", self.register_with_wallpaper_provider)        
        self.add_event(f"{self.skill_id}.get.wallpaper.collection", self.supply_wallpaper_collection)

    def collect_wallpapers(self):
        wallpaper_folder = "/usr/share/wallpapers"
        return [f"{wallpaper_folder}/{f}" for f in os.listdir(wallpaper_folder)]
    
    def register_with_wallpaper_provider(self, message):
        self.bus.emit(Message("ovos.wallpaper.manager.register.provider",
                              data={"provider_name": self.skill_id,
                                    "provider_display_name": "Example Wallpaper Provider"}))
    
    def supply_wallpaper_collection(self, message):
        wp = self.collect_wallpapers()
        self.bus.emit(Message("ovos.wallpaper.manager.collect.collection.response",
                              data={"provider_name": self.skill_id,
                                    "wallpaper_collection": wp}))
```

## Example Implementation in a Wallpaper Provider Skill Not Providing a Collection of Wallpapers:

``` python

def ExampleWallpaperProvider(OVOSSkill):
    def initialize(self):
        self.add_event("ovos.wallpaper.manager.loaded", self.register_with_wallpaper_provider)
        self.add_event(f"{self.skill_id}.get.new.wallpaper", self.supply_new_wallpaper)
    
    def register_with_wallpaper_provider(self, message):
        self.bus.emit(Message("ovos.wallpaper.manager.register.provider",
                              data={"provider_name": self.skill_id,
                                    "provider_display_name": "Example Wallpaper Provider"}))
    
    def supply_new_wallpaper(self, message):
        # Get a new wallpaper from some online source
        # and set it as the wallpaper on every request for a new wallpaper
        url = "https://example.com/wallpaper.jpg"
        self.bus.emit(Message("ovos.wallpaper.manager.set.wallpaper",
                              data={"url": url}))
```
