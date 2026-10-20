import QtQuick

// Sideways scrolling for a horizontal strip, without stealing the page's vertical wheel.
// Qt routes wheel events by direction, so: one handler for real horizontal deltas
// (touchpad swipe, tilt wheel) and one for Shift + vertical wheel. A plain vertical wheel
// matches neither and goes on to the page. (Declining inside a handler does NOT pass the
// event on to an ancestor's handler — that's why this isn't one handler that declines.)
Item {
    id: side
    property Flickable flick

    function scrollBy(dx) {
        const max = Math.max(0, flick.contentWidth - flick.width)
        flick.contentX = Math.max(0, Math.min(max, flick.contentX - dx))
    }

    WheelHandler {
        parent: side.flick
        target: null
        orientation: Qt.Horizontal
        onWheel: (ev) => side.scrollBy(ev.pixelDelta.x !== 0 ? ev.pixelDelta.x : ev.angleDelta.x)
    }
    WheelHandler {
        parent: side.flick
        target: null
        orientation: Qt.Vertical
        acceptedModifiers: Qt.ShiftModifier
        onWheel: (ev) => side.scrollBy(ev.pixelDelta.y !== 0 ? ev.pixelDelta.y : ev.angleDelta.y)
    }
}
