import QtQuick
import QtQuick.Controls.Basic

// Slider bound to a live value. While the user drags, the live value can't yank the
// handle back (the binding pauses); `moved` carries the user's value out.
Slider {
    id: control
    property real liveValue: 0
    property bool follow: true            // false: a choice the user makes (not a live value)
    property var trackGradient: null     // optional list of colours for a gradient track
    from: 1; to: 100
    implicitHeight: 28

    Binding on value { value: control.liveValue; when: control.follow && !control.pressed; restoreMode: Binding.RestoreNone }

    background: Rectangle {
        x: control.leftPadding; y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth; height: 6; radius: 3
        color: Theme.lineStrong
        gradient: control.trackGradient ? grad : null
        Gradient {
            id: grad
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: control.trackGradient ? control.trackGradient[0] : "black" }
            GradientStop { position: 1; color: control.trackGradient ? control.trackGradient[1] : "black" }
        }
        Rectangle {
            visible: !control.trackGradient
            width: control.visualPosition * parent.width; height: parent.height; radius: 3
            color: Theme.accent
        }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: 18; height: 18; radius: 9
        color: Theme.text
        border.color: Theme.ground; border.width: 2
    }
}
