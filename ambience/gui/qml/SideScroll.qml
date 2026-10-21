import QtQuick

// Wheel routing for a horizontal strip that stays draggable (an interactive Flickable
// would otherwise turn a vertical wheel into sideways scrolling and swallow it).
// Qt routes wheel events to handlers by direction and modifiers:
//   horizontal deltas (touchpad swipe, tilt wheel) and Shift + wheel → scroll the strip;
//   a plain vertical wheel → handed to the page's FastWheel, so the page scrolls.
// (A handler that merely declines does NOT pass the event on to an ancestor's handler,
// which is why the vertical case is forwarded explicitly.)
Item {
    id: side
    property Flickable flick
    property var pageWheel: null       // the page's FastWheel

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
    WheelHandler {
        parent: side.flick
        target: null
        orientation: Qt.Vertical
        acceptedModifiers: Qt.NoModifier
        enabled: side.pageWheel !== null
        onWheel: (ev) => side.pageWheel.handle(ev)
    }
}
