# OVOS PHAL Plugin Wallpaper Manager

This PHAL plugin gives OpenVoiceOS a central interface for wallpaper management. It works with homescreens and other desktop environments. The interface lists the wallpapers available from each registered provider, and it sets a wallpaper from that list. A provider can be a local source that reads wallpapers from the file system, or a remote source that reads wallpapers from a URL.

### Supported desktop environments

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

Platform support comes from [OpenVoiceOS/wallpaper_changer](https://github.com/OpenVoiceOS/wallpaper_changer).

### Install

`pip install ovos-PHAL-plugin-wallpaper-manager`

## Event and API reference

### Register and activate a wallpaper provider

A wallpaper provider must register with the central wallpaper management interface. To register, send this event:

``` python
    # ovos.wallpaper.manager.register.provider
    # type: Request
    # description: Register a wallpaper provider to the plugin
    # data required:
        # provider_name = typically the self.skill_id of the skill that provides the wallpaper provider
        # provider_display_name = A display name for the wallpaper provider, that will be displayed on the selection screens
        # (optional) provider_configurable = True if the wallpaper provider is configurable, False if not
```

When registration succeeds, the wallpaper management interface responds with this event:

``` python
    # ovos.phal.wallpaper.manager.provider.registered
    # type: Response
    # description: Registration successful
```

To activate a wallpaper provider, send this event:

``` python
    # ovos.wallpaper.manager.set.active.provider
    # type: Request
    # description: Activate a wallpaper provider
    # data required:
        # provider_name = typically the self.skill_id of the skill that is the wallpaper provider
```

Note: The Wallpapers Settings UI handles this event on "smartspeaker" and "mobile" GUI platforms. A skill or wallpaper provider must not send this event unless it needs to force an override of the current provider.

### Wallpaper collection API

A wallpaper provider can send a collection of wallpapers to the wallpaper management interface. This step is optional. Some providers keep their own collection of wallpapers, and some depend on an online source instead.

After a wallpaper provider registers, the wallpaper management interface sends it an event to request a collection of wallpapers. A provider that wants to supply wallpapers listens for this signal:

``` python
    # {provider_name}.get.wallpaper.collection
    # type: Request
    # description: Request a collection of wallpapers from the wallpaper provider
```

The provider responds to that signal with this event:

``` python
    # ovos.wallpaper.manager.collect.collection.response
    # type: Response
    # description: Response to the wallpaper collection request
    # data required:
        # provider_name = typically the self.skill_id of the skill that provides the wallpaper provider
        # wallpaper_collection = a list of full wallpaper paths that are available from the wallpaper provider
```

A wallpaper provider can also ask the wallpaper management interface to update its wallpaper collection at any time, by sending this event:

``` python
    # ovos.wallpaper.manager.update.collection
    # type: Request
    # description: Request the wallpaper management interface to update its wallpaper collection
    # data required:
        # provider_name = typically the self.skill_id of the skill that provides the wallpaper provider
```

### Wallpaper request for providers without a collection

If a wallpaper provider does not supply a collection of wallpapers, the wallpaper management interface always sends it an event to request a new wallpaper. The provider must listen for this signal:

``` python
    # {provider_name}.get.new.wallpaper
    # type: Request
    # description: Request a new wallpaper from the wallpaper provider
```

The provider must respond to that signal with this event:

``` python
    # ovos.wallpaper.manager.set.wallpaper
    # type: Response
    # description: Response to the wallpaper request to set new wallpaper
    # data required:
        # url = the full path of the wallpaper that is to be set
```

### Get and set wallpaper API

To get the current wallpaper, the wallpaper management interface sends this event:

``` python
    # ovos.wallpaper.manager.get.wallpaper
    # type: Request
    # description: Request the wallpaper management interface to get the current wallpaper
```

The wallpaper management interface responds to that event with this event:

``` python
    # ovos.wallpaper.manager.get.wallpaper.response
    # type: Response
    # description: Response to the wallpaper request to get the current wallpaper
    # data sent:
        # url = the full path of the current wallpaper
```

To set a wallpaper, send this event to the wallpaper management interface:

``` python
    # ovos.wallpaper.manager.set.wallpaper
    # type: Request
    # description: Request the wallpaper management interface to set a new wallpaper
    # data required:
        # url = the full path of the wallpaper that is to be set
```

Note:
- On platforms that support a homescreen, this event sets the homescreen wallpaper.
- On platforms without a homescreen, such as a desktop, this event sets the desktop wallpaper.

### Change wallpaper API

Any skill or event can ask the wallpaper management interface to change the wallpaper, by sending this event:

``` python
    # ovos.wallpaper.manager.change.wallpaper
    # type: Request
    # description: Request the wallpaper management interface to change the wallpaper
```

Note:
- If the selected provider supplies a collection of wallpapers, the wallpaper management interface picks the next wallpaper from that collection and sets it.
- If the selected provider does not supply a collection, the wallpaper management interface asks the provider for a new wallpaper.

### Auto-rotate wallpapers API

To turn on automatic wallpaper rotation, send this event:

``` python
    # ovos.wallpaper.manager.enable.auto.rotation
    # type: Request
    # description: Request the wallpaper management interface to enable auto rotate and set an wallpaper rotation interval
    # data required:
        # rotation_time = the time in seconds at which the wallpapers should be rotated
```

To turn off automatic wallpaper rotation, send this event:

``` python
    # ovos.wallpaper.manager.disable.auto.rotation
    # type: Request
    # description: Request the wallpaper management interface to disable auto rotate
```

## Example: wallpaper provider skill with a collection

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

## Example: wallpaper provider skill without a collection

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

## Related projects

- [OpenVoiceOS/wallpaper_changer](https://github.com/OpenVoiceOS/wallpaper_changer) — platform-specific wallpaper backend used by this plugin.
- [OpenVoiceOS/skill-ovos-homescreen](https://github.com/OpenVoiceOS/skill-ovos-homescreen) — homescreen skill that consumes this interface on ovos-shell.
