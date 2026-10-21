pragma Singleton
import QtQuick

// The mockup's tokens: a near-black ground so colour comes from the lights,
// one warm accent for actions.
QtObject {
    readonly property color ground: "#0d0e12"
    readonly property color sidebar: "#121318"
    readonly property color surface: "#17191f"
    readonly property color raised: "#1f222a"
    readonly property color well: "#1b1d24"
    readonly property color line: "#23262e"
    readonly property color lineStrong: "#2a2e37"
    readonly property color text: "#f2f3f5"
    readonly property color textSoft: "#d6dae1"
    readonly property color muted: "#a7adb8"
    readonly property color mutedNav: "#b4bac4"
    readonly property color accent: "#ffb547"
    readonly property color accentInk: "#1a1205"
    readonly property color ok: "#5fd38d"
    readonly property color glowBase: "#121318"
    // How long on-screen colours take to settle into a new value: about as long as the
    // lamps' own fade, so the app glides along instead of snapping (or lagging visibly).
    // Both tunables are set from Settings (Main.qml binds them); these are the defaults.
    property int fadeMs: 700
    // Wheel scrolling: pixels per "line"; a notch is the system's lines-per-scroll (Plasma
    // default 3) × this ≈ 100 px. Same for every mouse: wheels report notches, not DPI.
    property real wheelPixelsPerLine: 34
}
