import QtQuick

// Mouse-wheel scrolling at a normal desktop pace — Qt's Flickable default is sluggish.
// ~120 px per wheel notch with a short ease-out; touchpads keep their own pixel deltas.
WheelHandler {
    id: wheel
    property Flickable flick
    property real notchPixels: 120
    property real goal: 0
    target: null
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad

    onWheel: (ev) => {
        if (!flick) return
        const dy = ev.pixelDelta.y !== 0 ? ev.pixelDelta.y : ev.angleDelta.y / 120 * notchPixels
        if (dy === 0) { ev.accepted = false; return }
        const max = Math.max(0, flick.contentHeight - flick.height)
        const from = ease.running ? goal : flick.contentY
        goal = Math.max(0, Math.min(max, from - dy))
        if (ev.pixelDelta.y !== 0) { ease.stop(); flick.contentY = goal }   // touchpad: follow exactly
        else { ease.to = goal; ease.restart() }
    }

    property NumberAnimation ease: NumberAnimation {
        target: wheel.flick; property: "contentY"
        duration: 140; easing.type: Easing.OutCubic
    }
}
