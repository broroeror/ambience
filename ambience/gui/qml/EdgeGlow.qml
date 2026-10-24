import QtQuick

// A soft inner glow around the window's edge in the lights' colours: their current
// colours at rest, the streamed colours (pulsing with the music) while syncing. Each
// light colours the stretch of edge nearest to where it sits in the room. Drawn by a
// small shader (shaders/edgeglow.frag); purely decorative, so it never takes input.
ShaderEffect {
    id: glow
    objectName: "edgeGlow"
    readonly property var settings: backend.settings
    readonly property var lamps: backend.sync.edgeLamps
    readonly property bool syncing: backend.sync.syncing
    visible: settings.edgeGlow && (syncing || !settings.edgeGlowSyncOnly) && lamps.length > 0
    enabled: false

    property size size: Qt.size(width, height)
    property real reach: settings.edgeGlowWidth
    property real strength: settings.edgeGlowStrength / 100
    property real spread: Math.max(width, height) * 0.22
    Behavior on strength { NumberAnimation { duration: Theme.fadeMs } }

    // Streamed colours arrive ~30/s: glide between them just enough to hide the steps.
    // At rest, fade like every other colour in the app.
    readonly property int fade: syncing ? 70 : Theme.fadeMs
    function col(i) { return i < lamps.length ? Qt.rgba(lamps[i].rgb[0], lamps[i].rgb[1], lamps[i].rgb[2], 1) : Qt.rgba(0, 0, 0, 0) }
    function at(i) { return i < lamps.length ? Qt.point(lamps[i].anchor[0], lamps[i].anchor[1]) : Qt.point(0.5, 0.5) }

    property color c0: col(0); property color c1: col(1); property color c2: col(2); property color c3: col(3)
    property color c4: col(4); property color c5: col(5); property color c6: col(6); property color c7: col(7)
    property point p0: at(0); property point p1: at(1); property point p2: at(2); property point p3: at(3)
    property point p4: at(4); property point p5: at(5); property point p6: at(6); property point p7: at(7)
    Behavior on c0 { ColorAnimation { duration: glow.fade } }
    Behavior on c1 { ColorAnimation { duration: glow.fade } }
    Behavior on c2 { ColorAnimation { duration: glow.fade } }
    Behavior on c3 { ColorAnimation { duration: glow.fade } }
    Behavior on c4 { ColorAnimation { duration: glow.fade } }
    Behavior on c5 { ColorAnimation { duration: glow.fade } }
    Behavior on c6 { ColorAnimation { duration: glow.fade } }
    Behavior on c7 { ColorAnimation { duration: glow.fade } }

    fragmentShader: "../shaders/edgeglow.frag.qsb"
}
