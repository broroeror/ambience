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

    // Same wheel-vs-touchpad rule as FastWheel: no scroll phase = a wheel (go by angle,
    // 120 per notch → ~100 px); a phase = a touchpad gesture (pixels 1:1).
    function amount(ev, horizontal) {
        const px = horizontal ? ev.pixelDelta.x : ev.pixelDelta.y
        const ang = horizontal ? ev.angleDelta.x : ev.angleDelta.y
        if (ev.phase !== Qt.NoScrollPhase && px !== 0) return px
        return ang / 120 * Qt.styleHints.wheelScrollLines * Theme.wheelPixelsPerLine
    }

    function scrollBy(dx) {
        const max = Math.max(0, flick.contentWidth - flick.width)
        flick.contentX = Math.max(0, Math.min(max, flick.contentX - dx))
    }

    WheelHandler {
        parent: side.flick
        target: null
        orientation: Qt.Horizontal
        onWheel: (ev) => side.scrollBy(side.amount(ev, true))
    }
    WheelHandler {
        parent: side.flick
        target: null
        orientation: Qt.Vertical
        acceptedModifiers: Qt.ShiftModifier
        onWheel: (ev) => side.scrollBy(side.amount(ev, false))
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
