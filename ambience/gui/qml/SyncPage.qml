import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Flickable {
    id: page
    readonly property var sync: backend.sync
    readonly property bool active: sync.state === "running" || sync.state === "starting"
    contentHeight: col.implicitHeight + 64
    clip: true
    ScrollBar.vertical: ScrollBar {}
    FastWheel { flick: page }

    ColumnLayout {
        id: col
        x: 36; y: 28; width: page.width - 72
        spacing: 22

        RowLayout {   // header
            Layout.fillWidth: true
            spacing: 14
            Label { text: "Sync"; color: Theme.text; font.pixelSize: 28; font.weight: Font.ExtraBold; Layout.fillWidth: true }
            Label { text: "Entertainment area"; color: Theme.muted }
            ComboBox {
                id: areaBox
                enabled: !page.active
                model: page.sync.areas
                textRole: "name"
                valueRole: "id"
                implicitHeight: 44; implicitWidth: 240
                currentIndex: Math.max(0, indexOfValue(page.sync.area.id || ""))
                onActivated: page.sync.chooseArea(currentValue)
                contentItem: Label { leftPadding: 14; text: areaBox.displayText + "  ·  " + (page.sync.area.lights || 0) + " lights"; color: Theme.text; font.weight: Font.Bold; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                background: Rectangle { radius: 12; color: Theme.surface; border.color: Theme.lineStrong }
                popup.background: Rectangle { radius: 12; color: Theme.raised; border.color: Theme.lineStrong }
                delegate: ItemDelegate {
                    required property var modelData
                    width: areaBox.width
                    contentItem: Label { text: modelData.name + "  ·  " + modelData.lights + " lights"; color: Theme.text }
                    background: Rectangle { color: parent.highlighted ? Theme.lineStrong : "transparent"; radius: 8 }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 24

            Rectangle {   // live preview
                Layout.fillWidth: true
                Layout.preferredHeight: previewCol.implicitHeight + 40
                Layout.alignment: Qt.AlignTop
                radius: 18; color: Theme.surface; border.color: Theme.line
                ColumnLayout {
                    id: previewCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20 }
                    spacing: 14
                    RowLayout {
                        Label { text: "LIVE PREVIEW"; color: Theme.muted; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1; Layout.fillWidth: true }
                        Label { text: page.sync.rateText || (page.active ? "Starting…" : "Not syncing"); color: Theme.muted; font.pixelSize: 12 }
                    }
                    Flow {
                        id: flow
                        Layout.fillWidth: true
                        spacing: 20
                        // side by side when there's room for both, otherwise stacked full-width
                        readonly property bool sideBySide: previewCol.width >= 300 + 20 + 340
                        Column {
                            spacing: 8
                            width: flow.sideBySide ? previewCol.width - 340 - 20 : Math.min(previewCol.width, 440)
                            Rectangle {
                                width: parent.width; height: width * 9 / 16
                                radius: 10; color: Theme.glowBase; border.color: Theme.lineStrong; clip: true
                                Row {   // music: what the lights are listening to
                                    visible: page.sync.mode === "music" && page.sync.state === "running"
                                    anchors.centerIn: parent
                                    spacing: 24
                                    Repeater {
                                        model: [["bass", "Bass"], ["mids", "Mids"], ["highs", "Highs"]]
                                        delegate: Column {
                                            required property var modelData
                                            required property int index
                                            spacing: 6
                                            Rectangle {
                                                width: 46; height: 140; radius: 8; color: Theme.well
                                                Rectangle {
                                                    anchors.bottom: parent.bottom; width: parent.width; radius: 8
                                                    height: Math.max(6, parent.height * (page.sync.bands[modelData[0]] || 0))
                                                    color: Theme.lightAt(index / 2)
                                                    Behavior on color { ColorAnimation { duration: 120 } }
                                                    Behavior on height { NumberAnimation { duration: 110 } }
                                                }
                                            }
                                            Label { anchors.horizontalCenter: parent.horizontalCenter; text: modelData[1]; color: Theme.muted; font.pixelSize: 12 }
                                        }
                                    }
                                    Rectangle {   // flashes on every beat
                                        id: beatDot
                                        width: 46; height: 46; radius: 23; y: 47
                                        color: Theme.lightAt(0.5); opacity: 0.15
                                        Behavior on color { ColorAnimation { duration: 120 } }
                                        property int lastBeat: 0
                                        Connections {
                                            target: page.sync
                                            function onPreviewChanged() {
                                                if (page.sync.beatCount !== beatDot.lastBeat) { beatDot.lastBeat = page.sync.beatCount; flash.restart() }
                                            }
                                        }
                                        SequentialAnimation on opacity {
                                            id: flash; running: false
                                            NumberAnimation { to: 1; duration: 40 }
                                            NumberAnimation { to: 0.15; duration: 260 }
                                        }
                                    }
                                }
                                Image {
                                    anchors.fill: parent; anchors.margins: 1
                                    visible: page.sync.mode === "screen" && page.sync.state === "running"
                                    source: "image://sync/frame/" + page.sync.frameVersion
                                    smooth: true; cache: false
                                }
                                Label {
                                    anchors.centerIn: parent; visible: page.sync.state !== "running"
                                    text: page.sync.mode === "music" ? "The music the lights hear appears here" : "What the lights see appears here"; color: Theme.muted
                                }
                            }
                            Label { text: page.sync.mode === "music" ? "What’s playing on your speakers, as the lights hear it" : "Your screen, as the lights sample it"; color: Theme.muted; font.pixelSize: 12 }
                        }
                        Column {
                            spacing: 8
                            Rectangle {   // top-down map: screen along the front (top) edge
                                id: map
                                width: 340; height: 340
                                radius: 14; color: Theme.sidebar; border.color: Theme.lineStrong
                                Rectangle { x: 110; width: 120; y: 6; height: 6; radius: 3; color: Theme.textSoft }
                                Label { anchors.horizontalCenter: parent.horizontalCenter; y: 16; text: page.sync.mode === "music" ? "front" : "screen"; color: Theme.muted; font.pixelSize: 11 }
                                Repeater {
                                    model: page.sync.lamps
                                    delegate: Item {
                                        required property var modelData
                                        x: 20 + (modelData.x + 1) / 2 * 300 - 15
                                        y: 20 + (1 - modelData.y) / 2 * 300 - 15
                                        width: 30; height: 30
                                        property color lit: modelData.colour
                                        Behavior on lit { ColorAnimation { duration: 120 } }
                                        Rectangle {   // halo
                                            anchors.centerIn: parent; width: 58; height: 58; radius: 29
                                            color: Qt.rgba(parent.lit.r, parent.lit.g, parent.lit.b, page.sync.state === "running" ? 0.3 : 0)
                                        }
                                        Rectangle {
                                            anchors.fill: parent; radius: 15; color: parent.lit
                                            border.color: Qt.rgba(1, 1, 1, 0.25)
                                            Label { anchors.centerIn: parent; text: modelData.id; color: "#0d0e12"; font.pixelSize: 11; font.weight: Font.ExtraBold }
                                        }
                                    }
                                }
                            }
                            Label { text: "Light positions from the Hue app’s area setup"; color: Theme.muted; font.pixelSize: 12 }
                        }
                    }
                }
            }

            Rectangle {   // controls
                Layout.preferredWidth: 340
                Layout.alignment: Qt.AlignTop
                Layout.preferredHeight: controls.implicitHeight + 40
                radius: 18; color: Theme.surface; border.color: Theme.line
                ColumnLayout {
                    id: controls
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20 }
                    spacing: 18

                    ColumnLayout {
                        spacing: 8
                        Label { text: "Mode"; color: Theme.muted }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Repeater {
                                model: [["screen", "Screen"], ["music", "Music"]]
                                delegate: Button {
                                    required property var modelData
                                    Layout.fillWidth: true; implicitHeight: 44
                                    enabled: !page.active
                                    readonly property bool on: page.sync.mode === modelData[0]
                                    onClicked: page.sync.setMode(modelData[0])
                                    contentItem: Label { text: modelData[1]; color: parent.on ? Theme.text : Theme.mutedNav; font.weight: parent.on ? Font.ExtraBold : Font.Bold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                    background: Rectangle { radius: 9; color: parent.on ? Theme.lineStrong : Theme.well }
                                }
                            }
                        }
                    }
                    ColumnLayout {   // music colours
                        visible: page.sync.mode === "music"
                        spacing: 8
                        Label { text: "Colours"; color: Theme.muted }
                        ComboBox {
                            id: palBox
                            Layout.fillWidth: true; implicitHeight: 48
                            model: page.sync.palettes
                            textRole: "name"; valueRole: "id"
                            currentIndex: Math.max(0, indexOfValue(page.sync.palette.id || ""))
                            onActivated: page.sync.choosePalette(currentValue)
                            contentItem: RowLayout {
                                spacing: 10
                                Glow { Layout.leftMargin: 8; Layout.preferredWidth: 46; Layout.preferredHeight: 30; topRadius: 8; bottomRadius: 8; colors: page.sync.palette.glow || [] }
                                Label { text: page.sync.palette.name || ""; color: Theme.text; font.weight: Font.Bold; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                            background: Rectangle { radius: 12; color: Theme.well; border.color: Theme.lineStrong }
                            popup.background: Rectangle { radius: 12; color: Theme.raised; border.color: Theme.lineStrong }
                            popup.height: Math.min(420, popup.contentItem.implicitHeight + 12)
                            delegate: ItemDelegate {
                                required property var modelData
                                width: palBox.width
                                contentItem: RowLayout {
                                    spacing: 10
                                    Glow { Layout.preferredWidth: 40; Layout.preferredHeight: 26; topRadius: 7; bottomRadius: 7; colors: modelData.glow }
                                    Label { text: modelData.name; color: Theme.text; Layout.fillWidth: true; elide: Text.ElideRight }
                                }
                                background: Rectangle { color: parent.highlighted ? Theme.lineStrong : "transparent"; radius: 8 }
                            }
                        }
                    }
                    ColumnLayout {
                        spacing: 8
                        Label { text: "Intensity"; color: Theme.muted }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Repeater {
                                model: [["subtle", "Subtle"], ["moderate", "Moderate"], ["high", "High"], ["intense", "Intense"]]
                                delegate: Button {
                                    required property var modelData
                                    Layout.fillWidth: true; implicitHeight: 44
                                    readonly property bool on: page.sync.intensity === modelData[0]
                                    onClicked: page.sync.setIntensity(modelData[0])
                                    contentItem: Label { text: modelData[1]; color: parent.on ? Theme.text : Theme.mutedNav; font.weight: parent.on ? Font.ExtraBold : Font.Bold; font.pixelSize: 13; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                    background: Rectangle { radius: 9; color: parent.on ? Theme.lineStrong : Theme.well }
                                }
                            }
                        }
                    }
                    ColumnLayout {
                        spacing: 6
                        RowLayout {
                            Label { text: "Brightness"; color: Theme.muted; Layout.fillWidth: true }
                            Label { text: Math.round(briSlider.value) + "%"; color: Theme.text }
                        }
                        AmberSlider {
                            id: briSlider
                            Layout.fillWidth: true
                            from: 5; to: 100
                            liveValue: page.sync.brightness
                            onMoved: page.sync.setBrightness(value)
                        }
                    }
                    Rectangle {
                        // only a concern for SCREEN sync — a music area is exactly right for music
                        visible: page.sync.mode === "screen" && (page.sync.area.type || "") !== "screen" && (page.sync.area.type || "") !== ""
                        Layout.fillWidth: true
                        implicitHeight: hint.implicitHeight + 24
                        radius: 12; color: "#1d1a12"; border.color: "#4a3d1c"
                        Label {
                            id: hint
                            anchors.fill: parent; anchors.margins: 12
                            wrapMode: Text.Wrap; color: "#f0dcb4"; font.pixelSize: 13
                            text: "This area was set up for " + (page.sync.area.type || "music") + ", with lights around the room. For screen sync, an area with lights placed around your monitor works best — you can add one in the Hue app."
                        }
                    }
                    Label {
                        visible: page.sync.state === "error"
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                        text: page.sync.message; color: "#ffb4bb"
                    }
                    Button {
                        id: go
                        Layout.fillWidth: true; implicitHeight: 52
                        enabled: page.sync.state !== "starting" && !!page.sync.area.id
                        text: page.sync.state === "running" ? "Stop sync" : page.sync.state === "starting" ? "Starting…" : "Start sync"
                        onClicked: page.sync.state === "running" ? page.sync.stop() : page.sync.start()
                        contentItem: Label { text: go.text; color: page.sync.state === "running" ? Theme.text : Theme.accentInk; font.weight: Font.ExtraBold; font.pixelSize: 16; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        background: Rectangle { radius: 26; color: page.sync.state === "running" ? Theme.lineStrong : (go.down ? Qt.darker(Theme.accent, 1.15) : Theme.accent) }
                    }
                }
            }
        }
    }
}
