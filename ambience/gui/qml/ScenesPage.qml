import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Effects

Item {
    id: page
    readonly property var scene: backend.scene

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Flickable {
            id: main
            Layout.fillWidth: true; Layout.fillHeight: true
            contentHeight: col.implicitHeight + 56
            clip: true
            ScrollBar.vertical: ScrollBar {}

            ColumnLayout {
                id: col
                x: 36; y: 28; width: main.width - 72
                spacing: 18

                Label { text: "Scenes"; color: Theme.text; font.pixelSize: 28; font.weight: Font.ExtraBold }
                Label {
                    text: "Click a scene to see its options · right-click for Play, Play dynamic and your own photo"
                    color: Theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true
                }

                Repeater {   // one two-row strip per room / zone
                    model: backend.sceneGroupsModel
                    delegate: ColumnLayout {
                        required property var item
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                        spacing: 10
                        visible: item.count > 0
                        Label {
                            text: (item.name + " · " + item.count + (item.count === 1 ? " scene" : " scenes")).toUpperCase()
                            color: Theme.muted; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1
                        }
                        SceneStrip {
                            Layout.fillWidth: true
                            Layout.preferredHeight: implicitHeight
                            model: backend.sceneModelFor(item.id)
                            selectOnClick: true
                        }
                    }
                }

                ColumnLayout {   // the gallery
                    Layout.fillWidth: true
                    Layout.topMargin: 14
                    spacing: 6
                    Label { text: "AMBIENCE GALLERY"; color: Theme.muted; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1 }
                    Label {
                        text: "Original presets. Adding one creates a real scene on the bridge, so your phone sees it too."
                        color: Theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                }
                GridView {
                    id: gallery
                    Layout.fillWidth: true
                    Layout.preferredHeight: 2 * cellHeight
                    flow: GridView.FlowTopToBottom
                    cellWidth: 212; cellHeight: 148
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickableDirection: Flickable.HorizontalFlick
                    ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
                    model: backend.galleryModel
                    delegate: Rectangle {
                        id: preset
                        required property var item
                        width: 200; height: 136
                        radius: 16
                        color: Theme.surface
                        border.color: pHover.hovered ? Theme.lineStrong : Theme.line
                        HoverHandler { id: pHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: { addMenu.preset = preset.item; addMenu.popup() } }
                        Glow { x: 1; y: 1; width: parent.width - 2; height: 78; topRadius: 15; colors: preset.item.glow }
                        Column {
                            x: 14; y: 88; width: parent.width - 28
                            spacing: 2
                            Label { text: preset.item.name; color: Theme.text; font.weight: Font.ExtraBold; font.pixelSize: 15; elide: Text.ElideRight; width: parent.width }
                            Label { text: preset.item.mood; color: Theme.muted; font.pixelSize: 12; elide: Text.ElideRight; width: parent.width }
                        }
                    }
                    ThemedMenu {
                        id: addMenu
                        property var preset: ({})
                        title: "Add to…"
                        Instantiator {   // a Repeater can't populate a Menu; an Instantiator can
                            model: backend.groupChoices
                            delegate: ThemedMenuItem {
                                required property var modelData
                                text: "Add to " + modelData.name
                                onTriggered: backend.addPreset(addMenu.preset.id, modelData.id)
                            }
                            onObjectAdded: (i, obj) => addMenu.insertItem(i, obj)
                            onObjectRemoved: (i, obj) => addMenu.removeItem(obj)
                        }
                    }
                }
            }
        }

        Rectangle {   // the selected scene
            Layout.preferredWidth: Math.min(340, Math.max(290, page.width * 0.32)); Layout.fillHeight: true
            color: Theme.sidebar
            Rectangle { width: 1; height: parent.height; color: Theme.line }

            Label {
                visible: !page.scene.id
                anchors.centerIn: parent; width: parent.width - 48
                horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                text: "Pick a scene to see how it plays"
                color: Theme.muted
            }

            ColumnLayout {
                id: panel
                visible: !!page.scene.id
                anchors.fill: parent; anchors.margins: 24; anchors.topMargin: 28
                spacing: 18
                // The panel's controls are choices for the NEXT Play, so they don't follow the
                // bridge; they reset only when a different scene is selected.
                property bool dynamicMode: false
                readonly property string sceneId: page.scene.id || ""
                onSceneIdChanged: {
                    dynamicMode = page.scene.playing === "dynamic_palette"
                    speedSlider.value = page.scene.speed ?? 0.6
                    briSlider.value = page.scene.brightness ?? 100
                }

                Item {
                    Layout.fillWidth: true; Layout.preferredHeight: 150
                    Glow { anchors.fill: parent; topRadius: 16; bottomRadius: 16; colors: page.scene.glow || []; visible: !page.scene.photo }
                    Image {
                        id: bigPhoto
                        anchors.fill: parent; visible: false
                        source: page.scene.photo || ""; fillMode: Image.PreserveAspectCrop; sourceSize.width: 700; asynchronous: true
                    }
                    Item { id: bigMask; anchors.fill: parent; visible: false; layer.enabled: true; Rectangle { anchors.fill: parent; radius: 16 } }
                    MultiEffect { anchors.fill: parent; visible: !!page.scene.photo; source: bigPhoto; maskEnabled: true; maskSource: bigMask }
                }
                ColumnLayout {
                    spacing: 4
                    Label { text: page.scene.name || ""; color: Theme.text; font.pixelSize: 22; font.weight: Font.ExtraBold; elide: Text.ElideRight; Layout.fillWidth: true }
                    Label { text: (page.scene.groupName || "") + " · " + ((page.scene.glow || []).length) + ((page.scene.glow || []).length === 1 ? " colour" : " colours"); color: Theme.muted }
                }
                RowLayout {   // Static | Dynamic
                    Layout.fillWidth: true
                    visible: !!page.scene.dynamic
                    spacing: 4
                    Repeater {
                        model: [[false, "Static"], [true, "Dynamic"]]
                        delegate: Button {
                            required property var modelData
                            Layout.fillWidth: true; implicitHeight: 40
                            readonly property bool on: panel.dynamicMode === modelData[0]
                            onClicked: panel.dynamicMode = modelData[0]
                            contentItem: Label { text: modelData[1]; color: parent.on ? Theme.text : Theme.mutedNav; font.weight: parent.on ? Font.ExtraBold : Font.Bold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                            background: Rectangle { radius: 9; color: parent.on ? Theme.lineStrong : Theme.well }
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: panel.dynamicMode && !!page.scene.dynamic
                    spacing: 6
                    RowLayout {
                        Label { text: "Speed"; color: Theme.muted; Layout.fillWidth: true }
                        Label { text: speedSlider.value < 0.34 ? "Slow drift" : speedSlider.value < 0.67 ? "Gentle" : "Lively"; color: Theme.textSoft }
                    }
                    AmberSlider { id: speedSlider; Layout.fillWidth: true; from: 0; to: 1; follow: false }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    RowLayout {
                        Label { text: "Brightness"; color: Theme.muted; Layout.fillWidth: true }
                        Label { text: Math.round(briSlider.value) + "%"; color: Theme.text }
                    }
                    AmberSlider { id: briSlider; Layout.fillWidth: true; follow: false }
                }
                Item { Layout.fillHeight: true }
                Button {
                    id: play
                    Layout.fillWidth: true; implicitHeight: 48
                    text: "Play in " + (page.scene.groupName || "")
                    onClicked: backend.playScene(page.scene.id, panel.dynamicMode && !!page.scene.dynamic, speedSlider.value, briSlider.value)
                    contentItem: Label { text: play.text; color: Theme.accentInk; font.weight: Font.ExtraBold; font.pixelSize: 15; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                    background: Rectangle { radius: 24; color: play.down ? Qt.darker(Theme.accent, 1.15) : Theme.accent }
                }
            }
        }
    }
}
