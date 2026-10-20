import QtQuick
import QtQuick.Controls.Basic

// The amber pill switch from the mockups. Emits `toggled` from user action only, so a
// live update arriving from the bridge never echoes back as a command.
Switch {
    id: control
    property bool liveChecked: false
    // A Binding object (unlike a plain `checked: …`) survives the user's click, so the
    // switch keeps following the bridge afterwards.
    Binding on checked { value: control.liveChecked; restoreMode: Binding.RestoreNone }
    implicitWidth: 52
    implicitHeight: 30
    padding: 0
    indicator: Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: control.checked ? Theme.accent : Theme.lineStrong
        Behavior on color { ColorAnimation { duration: 120 } }
        Rectangle {
            width: parent.height - 6; height: width; radius: width / 2
            y: 3
            x: control.checked ? parent.width - width - 3 : 3
            color: control.checked ? Theme.accentInk : Theme.muted
            Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        }
    }
    contentItem: Item {}
}
