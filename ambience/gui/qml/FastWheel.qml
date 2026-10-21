import QtQuick

// Mouse-wheel scrolling at a normal desktop pace — Qt's Flickable default is sluggish.
// Mouse wheels go by notches (the system's "lines per scroll" × 60 px, eased); touchpads
// follow the fingers 1:1 via their pixel deltas. On Wayland a mouse wheel can report pixel
// deltas too, so the device type decides, not which delta happens to be present.
// Strips call handle() for vertical wheels over them, so the whole page shares one goal.
WheelHandler {
    id: wheel
    property Flickable flick
    property real notchPixels: Qt.styleHints.wheelScrollLines * 60
    property real goal: 0
    target: null
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    onWheel: (ev) => handle(ev)

    function handle(ev) {
        if (!flick) return
        const touchpad = ev.device && ev.device.type === PointerDevice.TouchPad
        const dy = touchpad ? (ev.pixelDelta.y !== 0 ? ev.pixelDelta.y : ev.angleDelta.y / 8)
                            : ev.angleDelta.y / 120 * notchPixels
        if (dy === 0) return
        const max = Math.max(0, flick.contentHeight - flick.height)
        const from = ease.running ? goal : flick.contentY
        goal = Math.max(0, Math.min(max, from - dy))
        if (touchpad) { ease.stop(); flick.contentY = goal }
        else { ease.to = goal; ease.restart() }
    }

    property NumberAnimation ease: NumberAnimation {
        target: wheel.flick; property: "contentY"
        duration: 160; easing.type: Easing.OutCubic
    }
}
