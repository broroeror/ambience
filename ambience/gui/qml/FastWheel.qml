import QtQuick

// Mouse-wheel scrolling at a normal desktop pace — Qt's Flickable default is sluggish.
// Wheels go by notches (the system's "lines per scroll" × Theme.wheelPixelsPerLine, eased); touchpads follow
// the fingers 1:1 via their pixel deltas.
// Wheel vs touchpad is decided by the scroll PHASE: touchpads report a gesture (begin /
// update / end), wheels report none. Neither the device type nor the deltas can be trusted:
// on this KWin/Wayland setup a hi-res mouse wheel arrives as device "touchpad" (type 4),
// 7–8 events per notch whose angle deltas sum to 120 but whose pixel deltas sum to ~15.
// Strips call handle() for vertical wheels over them, so the whole page shares one goal.
WheelHandler {
    id: wheel
    property Flickable flick
    property real notchPixels: Qt.styleHints.wheelScrollLines * Theme.wheelPixelsPerLine
    property real goal: 0
    target: null
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    onWheel: (ev) => handle(ev)

    function handle(ev) {
        if (!flick) return
        const touchpad = ev.phase !== Qt.NoScrollPhase
        if (backend.debugWheel)
            backend.debugLog("wheel: device=" + (ev.device ? ev.device.name + " type=" + ev.device.type : "?")
                             + " angleDelta=" + ev.angleDelta.y + " pixelDelta=" + ev.pixelDelta.y
                             + " phase=" + ev.phase + " inverted=" + ev.inverted
                             + " contentY=" + Math.round(flick.contentY) + " t=" + Date.now() % 100000)
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
