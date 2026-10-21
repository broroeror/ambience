import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Flickable {
    id: page
    readonly property var settings: backend.settings
    readonly property var br: settings.bridge
    contentHeight: col.implicitHeight + 64
    clip: true
    ScrollBar.vertical: ScrollBar {}
    FastWheel { flick: page }

    // One card per topic: a caption above, rows inside.
    component Card: Rectangle {
        default property alias rows: inner.data
        property string title
        Layout.fillWidth: true
        Layout.maximumWidth: 760
        implicitHeight: inner.implicitHeight + 40
        radius: 18; color: Theme.surface; border.color: Theme.line
        Label { x: 20; y: -26; text: parent.title; color: Theme.muted; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1 }
        ColumnLayout { id: inner; anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20 } spacing: 18 }
    }
    component Fact: RowLayout {
        property string label
        property string value
        visible: value !== ""
        Layout.fillWidth: true
        Label { text: parent.label; color: Theme.muted; Layout.preferredWidth: 150 }
        Label { text: parent.value; color: Theme.text; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
    }
    component Pill: Button {
        id: pill
        implicitHeight: 40
        contentItem: Label { text: pill.text; color: Theme.text; font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; leftPadding: 10; rightPadding: 10 }
        background: Rectangle { radius: 20; color: pill.hovered ? Theme.raised : Theme.well; border.color: "#343843" }
    }
    // A labelled slider with its value and a way back to the default.
    component Tuning: ColumnLayout {
        id: tuning
        property string label
        property string hint
        property string valueText
        property real from
        property real to
        property real stepSize: 1
        property real live
        property bool isDefault
        signal moved(real value)
        signal reset()
        Layout.fillWidth: true
        spacing: 6
        RowLayout {
            Label { text: tuning.label; color: Theme.text; font.weight: Font.Bold; Layout.fillWidth: true }
            Label { text: tuning.valueText; color: Theme.text }
            Label {
                visible: !tuning.isDefault
                text: "Reset"; color: Theme.accent; font.weight: Font.Bold; leftPadding: 10
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: tuning.reset() }
            }
        }
        AmberSlider {
            Layout.fillWidth: true
            from: tuning.from; to: tuning.to; stepSize: tuning.stepSize
            liveValue: tuning.live
            onMoved: tuning.moved(value)
        }
        Label { text: tuning.hint; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
    }

    ColumnLayout {
        id: col
        x: 40; y: 32; width: page.width - 80
        spacing: 48

        Label { text: "Settings"; color: Theme.text; font.pixelSize: 30; font.weight: Font.ExtraBold; Layout.bottomMargin: -4 }

        Card {
            title: "BRIDGE"
            RowLayout {
                spacing: 10
                Rectangle { width: 10; height: 10; radius: 5; color: backend.connected ? Theme.ok : Theme.accent }
                Label { text: page.br.name || "Hue Bridge"; color: Theme.text; font.pixelSize: 18; font.weight: Font.ExtraBold; Layout.fillWidth: true }
                Label { text: !backend.paired ? "Not paired" : backend.connected ? "Connected" : "Reconnecting…"; color: Theme.muted }
            }
            Fact { label: "Address"; value: page.br.host || "" }
            Fact { label: "Model"; value: page.br.model || "" }
            Fact { label: "Software"; value: page.br.software || "" }
            Fact { label: "Bridge ID"; value: page.br.id || "" }
            RowLayout {
                spacing: 14
                Pill { text: "Pair again…"; onClicked: backend.openPairing() }
                Label {
                    Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12
                    text: "For a new bridge, or if the bridge was reset. You’ll press the button on the bridge again."
                }
            }
        }

        Card {
            title: "FEEL"
            Tuning {
                label: "Scroll speed"
                valueText: Math.round(page.settings.scrollSpeed * 3) + " px per notch"
                hint: "How far one click of the mouse wheel moves a page. Touchpads always follow your fingers."
                from: 10; to: 90
                live: page.settings.scrollSpeed
                isDefault: page.settings.scrollSpeed === page.settings.defaults.scrollSpeed
                onMoved: (v) => page.settings.setScrollSpeed(v)
                onReset: page.settings.reset("scrollSpeed")
            }
            Tuning {
                label: "Colour fades"
                valueText: page.settings.fadeMs === 0 ? "Instant" : (page.settings.fadeMs / 1000).toFixed(page.settings.fadeMs % 100 ? 2 : 1) + " s"
                hint: "How long colours in the app take to glide to a new value. Around 0.7 s matches the lights themselves."
                from: 0; to: 2000; stepSize: 50
                live: page.settings.fadeMs
                isDefault: page.settings.fadeMs === page.settings.defaults.fadeMs
                onMoved: (v) => page.settings.setFadeMs(v)
                onReset: page.settings.reset("fadeMs")
            }
        }

        Card {
            title: "STARTUP"
            RowLayout {
                spacing: 16
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Label { text: "Start with the computer"; color: Theme.text; font.weight: Font.Bold }
                    Label {
                        Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12
                        text: "Ambience opens quietly in the tray when you log in, ready for sync from the tray menu."
                    }
                }
                Toggle {
                    liveChecked: page.settings.autostart
                    onToggled: page.settings.setAutostart(checked)
                }
            }
        }

        Card {
            title: "ABOUT"
            Fact { label: "Version"; value: page.settings.version }
            Fact { label: "Licence"; value: "MIT · fonts: Manrope (SIL Open Font Licence)" }
            Fact { label: "Sync log"; value: page.settings.logDir + "/sync.log" }
            RowLayout {
                spacing: 14
                Pill { text: "Open log folder"; onClicked: page.settings.openLogDir() }
                Item { Layout.fillWidth: true }
            }
            Label {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12
                text: "Ambience is an unofficial app, not affiliated with or endorsed by Signify or Philips Hue."
            }
        }
    }
}
