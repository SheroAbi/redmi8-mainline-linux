# phone-ui

GNOME tuned for the Redmi 8's notch screen: top bar clear of the notch, maximized windows, dark theme, dock.

    sudo extras/install.sh phone-ui

* The GNOME Shell extension `olive-display@redmi8` moves the clock out from
  under the notch, pads the top bar 34 px on both sides for the rounded
  corners, and opens normal app windows maximized, like on a phone.
* System defaults (`/etc/dconf/db/local.d/60-olive-phone-ui`): the extension
  and the Ubuntu dock enabled, dark Yaru, no edge tiling, dock favourites
  Firefox, Files, Terminal, Text Editor, Settings.

Log out and in again (or reboot) after installing. Users who already changed
one of these settings keep their own value.
