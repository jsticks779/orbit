// Orbit helper: put the Orbit card under the pointer and keep it on top.
// Wayland apps can't position their own windows; the shell can.

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const APP_ID = 'io.github.jsticks779.Orbit';
const CARD_TITLE = 'Orbit Panel';

export default class OrbitHelper extends Extension {
    enable() {
        this._created = global.display.connect('window-created', (_display, win) => this._onWindow(win));
    }

    disable() {
        if (this._created)
            global.display.disconnect(this._created);
        this._created = null;
    }

    _onWindow(win) {
        if (win.get_wm_class() !== APP_ID)
            return;
        const actor = win.get_compositor_private();
        if (!actor)
            return;
        // Hide until positioned so the card doesn't jump.
        actor.opacity = 0;
        const id = actor.connect('first-frame', () => {
            actor.disconnect(id);
            if (win.get_title() === CARD_TITLE)
                this._place(win);
            actor.opacity = 255;
        });
    }

    _place(win) {
        const [px, py] = global.get_pointer();
        const rect = win.get_frame_rect();
        const mon = global.display.get_monitor_index_for_rect(rect);
        const area = win.get_work_area_for_monitor(mon >= 0 ? mon : global.display.get_current_monitor());
        // Centre the card's orbit (about 48% down) on the pointer, kept on screen.
        let x = Math.round(px - rect.width / 2);
        let y = Math.round(py - rect.height * 0.48);
        x = Math.max(area.x, Math.min(x, area.x + area.width - rect.width));
        y = Math.max(area.y, Math.min(y, area.y + area.height - rect.height));
        win.move_frame(false, x, y);
        win.make_above();
    }
}
