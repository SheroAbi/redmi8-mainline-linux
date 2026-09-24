// Redmi 8 (olive): 720x1520 panel with a centred dew-drop notch and rounded
// corners. The clock normally sits right under the notch and the corner
// indicators are clipped; app windows are often wider than 720 px.
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class OliveDisplayExtension extends Extension {
    enable() {
        const panel = Main.panel;

        // Move the clock out of the notch, next to the activities button.
        this._dateContainer = panel.statusArea.dateMenu.container;
        this._dateParent = this._dateContainer.get_parent();
        this._dateParent.remove_child(this._dateContainer);
        panel._leftBox.add_child(this._dateContainer);

        // Side padding for the rounded corners (see stylesheet.css).
        panel.add_style_class_name('olive-cutout');

        // Phone behaviour: normal app windows open maximized.
        this._windowCreatedId = global.display.connect('window-created',
            (_display, window) => this._watchWindow(window));
        for (const actor of global.get_window_actors())
            this._maximize(actor.meta_window);
    }

    _watchWindow(window) {
        const actor = window.get_compositor_private();
        if (!actor) {
            GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                this._maximize(window);
                return GLib.SOURCE_REMOVE;
            });
            return;
        }
        const id = actor.connect('first-frame', () => {
            actor.disconnect(id);
            this._maximize(window);
        });
    }

    _maximize(window) {
        if (!window || window.get_window_type() !== Meta.WindowType.NORMAL)
            return;
        if (window.is_fullscreen() || !window.can_maximize() || window.get_transient_for())
            return;
        window.maximize(Meta.MaximizeFlags.BOTH);
    }

    disable() {
        if (this._windowCreatedId) {
            global.display.disconnect(this._windowCreatedId);
            this._windowCreatedId = 0;
        }
        Main.panel.remove_style_class_name('olive-cutout');
        if (this._dateContainer) {
            this._dateContainer.get_parent()?.remove_child(this._dateContainer);
            this._dateParent.add_child(this._dateContainer);
            this._dateContainer = null;
        }
    }
}
