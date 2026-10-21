import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// First run (or re-pair): find the bridge, then wait for its link button.
Rectangle {
    id: page
    color: Theme.ground
    readonly property var p: backend.pairing
    readonly property bool repair: backend.paired      // already paired → this is a re-pair

    Component.onCompleted: if (p.stage === "idle") p.search()
    onVisibleChanged: if (visible && (p.stage === "idle" || p.stage === "done")) p.search()

    Button {   // close (re-pair only)
        id: closeBtn
        visible: page.repair && page.p.stage !== "waiting"
        anchors { top: parent.top; right: parent.right; margins: 20 }
        implicitWidth: 44; implicitHeight: 44
        onClicked: backend.closePairing()
        Accessible.name: "Close"
        contentItem: Label { text: "×"; color: Theme.text; font.pixelSize: 24; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { radius: 22; color: closeBtn.hovered ? Theme.raised : Theme.surface; border.color: Theme.lineStrong }
    }

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(480, parent.width - 64)
        spacing: 22

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 12
            Rectangle {
                width: 34; height: 34; radius: 17; color: "transparent"; border.color: Theme.accent; border.width: 2
                Rectangle { anchors.centerIn: parent; width: 13; height: 13; radius: 7; color: Theme.accent }
            }
            Label { text: "Ambience"; color: Theme.text; font.pixelSize: 24; font.weight: Font.ExtraBold }
        }

        Label {
            Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
            color: Theme.text; font.pixelSize: 26; font.weight: Font.ExtraBold
            text: page.p.stage === "waiting" ? "Press the button on your bridge"
                : page.p.stage === "done" ? "Connected"
                : page.repair ? "Connect to your Hue Bridge" : "Let’s find your Hue Bridge"
        }

        // --- searching ---------------------------------------------------------------
        ColumnLayout {
            visible: page.p.stage === "searching"
            Layout.alignment: Qt.AlignHCenter
            spacing: 14
            Item {
                Layout.alignment: Qt.AlignHCenter
                width: 46; height: 46
                Rectangle {   // spinner: an amber arc on a faint ring
                    anchors.fill: parent; radius: 23; color: "transparent"; border.color: Theme.lineStrong; border.width: 4
                }
                Rectangle {
                    width: 12; height: 12; radius: 6; color: Theme.accent
                    x: 23 + 19 * Math.cos(spin.angle) - 6; y: 23 + 19 * Math.sin(spin.angle) - 6
                    QtObject { id: spin; property real angle: 0 }
                    NumberAnimation on x { running: false }
                }
                NumberAnimation { target: spin; property: "angle"; from: 0; to: 2 * Math.PI; duration: 1000; loops: Animation.Infinite; running: page.p.stage === "searching" }
            }
            Label { text: "Looking for your Hue Bridge on the network…"; color: Theme.muted; Layout.alignment: Qt.AlignHCenter }
        }

        // --- found ----------------------------------------------------------------------
        ColumnLayout {
            visible: page.p.stage === "found"
            Layout.fillWidth: true
            spacing: 12
            Repeater {
                model: page.p.bridges
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true; implicitHeight: 76
                    radius: 16; color: Theme.surface; border.color: Theme.line
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 16
                        spacing: 14
                        Rectangle {   // the bridge, drawn
                            width: 44; height: 44; radius: 12; color: "#e9eaee"
                            Rectangle { anchors.centerIn: parent; width: 22; height: 22; radius: 11; color: "#d3d5db"; border.color: "#c2c5cc" }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 3
                            Label { text: modelData.model; color: Theme.text; font.weight: Font.ExtraBold; font.pixelSize: 15 }
                            Label { text: modelData.host + " · " + modelData.id.slice(-6).toUpperCase(); color: Theme.muted; font.pixelSize: 13 }
                        }
                        Button {
                            id: connectBtn
                            text: "Connect"; implicitHeight: 42
                            onClicked: page.p.pairWith(modelData.host)
                            contentItem: Label { text: connectBtn.text; color: Theme.accentInk; font.weight: Font.ExtraBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                            background: Rectangle { implicitWidth: 110; radius: 21; color: connectBtn.down ? Qt.darker(Theme.accent, 1.15) : Theme.accent }
                        }
                    }
                }
            }
        }

        // --- waiting for the button ------------------------------------------------------
        ColumnLayout {
            visible: page.p.stage === "waiting"
            Layout.fillWidth: true
            spacing: 18
            Item {   // the bridge from above, its button pulsing
                Layout.alignment: Qt.AlignHCenter
                width: 150; height: 150
                Rectangle { anchors.centerIn: parent; width: 140; height: 140; radius: 34; color: "#e9eaee" }
                Rectangle {
                    id: ring
                    anchors.centerIn: parent; width: 70; height: 70; radius: 35
                    color: "transparent"; border.color: Theme.accent; border.width: 3
                    SequentialAnimation on scale {
                        running: page.p.stage === "waiting"; loops: Animation.Infinite
                        NumberAnimation { from: 1.0; to: 1.45; duration: 1100; easing.type: Easing.OutCubic }
                        PauseAnimation { duration: 200 }
                    }
                    SequentialAnimation on opacity {
                        running: page.p.stage === "waiting"; loops: Animation.Infinite
                        NumberAnimation { from: 1.0; to: 0.0; duration: 1100; easing.type: Easing.OutCubic }
                        PauseAnimation { duration: 200 }
                    }
                }
                Rectangle { anchors.centerIn: parent; width: 62; height: 62; radius: 31; color: "#d3d5db"; border.color: "#c2c5cc" }
            }
            Label {
                Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                text: "Press the big round button on top of the bridge once. Ambience is listening for it."
                color: Theme.textSoft
            }
            ColumnLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: 6
                Rectangle {
                    Layout.preferredWidth: 260; Layout.preferredHeight: 6; radius: 3; color: Theme.lineStrong
                    Rectangle {
                        width: parent.width * page.p.secondsLeft / page.p.waitSeconds; height: parent.height; radius: 3; color: Theme.accent
                        Behavior on width { NumberAnimation { duration: 250 } }
                    }
                }
                Label { Layout.alignment: Qt.AlignHCenter; text: page.p.secondsLeft + " s left"; color: Theme.muted; font.pixelSize: 13 }
            }
            Button {
                id: cancelWait
                Layout.alignment: Qt.AlignHCenter
                text: "Cancel"; implicitHeight: 40
                onClicked: page.p.cancel()
                contentItem: Label { text: cancelWait.text; color: Theme.text; font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { implicitWidth: 110; radius: 20; color: cancelWait.hovered ? Theme.lineStrong : Theme.surface; border.color: Theme.lineStrong }
            }
        }

        // --- connected ----------------------------------------------------------------------
        Rectangle {
            visible: page.p.stage === "done"
            Layout.alignment: Qt.AlignHCenter
            width: 84; height: 84; radius: 42; color: Theme.ok
            Label { anchors.centerIn: parent; text: "✓"; color: "#0d0e12"; font.pixelSize: 44; font.weight: Font.ExtraBold }
        }

        // --- error -----------------------------------------------------------------------
        Rectangle {
            visible: page.p.stage === "error"
            Layout.fillWidth: true
            implicitHeight: errText.implicitHeight + 28
            radius: 14; color: "#2a1518"; border.color: "#6b2a33"
            Label { id: errText; anchors.fill: parent; anchors.margins: 14; text: page.p.message; color: "#ffd0d4"; wrapMode: Text.Wrap }
        }
        Button {
            id: again
            visible: page.p.stage === "error"
            Layout.alignment: Qt.AlignHCenter
            text: "Search again"; implicitHeight: 44
            onClicked: page.p.search()
            contentItem: Label { text: again.text; color: Theme.accentInk; font.weight: Font.ExtraBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            background: Rectangle { implicitWidth: 160; radius: 22; color: Theme.accent }
        }

        // --- manual IP (found / error) ----------------------------------------------------------
        ColumnLayout {
            visible: page.p.stage === "found" || page.p.stage === "error"
            Layout.fillWidth: true
            Layout.topMargin: 6
            spacing: 8
            Label { text: "Or enter the bridge’s IP address"; color: Theme.muted; font.pixelSize: 13 }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                TextField {
                    id: ipField
                    Layout.fillWidth: true; implicitHeight: 44
                    placeholderText: "e.g. 192.168.1.20"
                    color: Theme.text; placeholderTextColor: Theme.muted
                    leftPadding: 14
                    inputMethodHints: Qt.ImhPreferNumbers
                    onAccepted: page.p.pairWith(text)
                    background: Rectangle { radius: 12; color: Theme.surface; border.color: ipField.activeFocus ? Theme.accent : Theme.lineStrong }
                }
                Button {
                    id: ipGo
                    text: "Connect"; implicitHeight: 44
                    enabled: ipField.text.trim().length > 6
                    onClicked: page.p.pairWith(ipField.text)
                    contentItem: Label { text: ipGo.text; color: ipGo.enabled ? Theme.text : Theme.muted; font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { implicitWidth: 110; radius: 22; color: Theme.surface; border.color: Theme.lineStrong }
                }
            }
        }
    }
}
