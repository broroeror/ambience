import QtQuick
import QtQuick.Shapes

// Hue around the rim, saturation from the centre (white) outwards. Qt's conical gradient
// runs counter-clockwise from 3 o'clock, so a point's hue is its counter-clockwise angle.
Item {
    id: wheel
    property color current: "white"
    signal picked(real hue, real saturation)

    readonly property real radius: Math.min(width, height) / 2
    readonly property real cx: width / 2
    readonly property real cy: height / 2

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeWidth: -1
            fillGradient: ConicalGradient {
                centerX: wheel.cx; centerY: wheel.cy; angle: 0
                GradientStop { position: 0.000; color: "#ff0000" }
                GradientStop { position: 0.167; color: "#ffff00" }
                GradientStop { position: 0.333; color: "#00ff00" }
                GradientStop { position: 0.500; color: "#00ffff" }
                GradientStop { position: 0.667; color: "#0000ff" }
                GradientStop { position: 0.833; color: "#ff00ff" }
                GradientStop { position: 1.000; color: "#ff0000" }
            }
            PathAngleArc { centerX: wheel.cx; centerY: wheel.cy; radiusX: wheel.radius; radiusY: wheel.radius; startAngle: 0; sweepAngle: 360 }
        }
        ShapePath {   // white at the centre fading out = saturation
            strokeWidth: -1
            fillGradient: RadialGradient {
                centerX: wheel.cx; centerY: wheel.cy; centerRadius: wheel.radius
                focalX: wheel.cx; focalY: wheel.cy
                GradientStop { position: 0.0; color: "#ffffffff" }
                GradientStop { position: 1.0; color: "#00ffffff" }
            }
            PathAngleArc { centerX: wheel.cx; centerY: wheel.cy; radiusX: wheel.radius; radiusY: wheel.radius; startAngle: 0; sweepAngle: 360 }
        }
    }

    Rectangle {  // marker at the light's current colour
        readonly property real a: Math.max(0, wheel.current.hsvHue) * 2 * Math.PI
        readonly property real d: wheel.current.hsvSaturation * (wheel.radius - 6)
        width: 26; height: 26; radius: 13
        x: wheel.cx + d * Math.cos(a) - width / 2
        y: wheel.cy - d * Math.sin(a) - height / 2
        color: wheel.current
        border.color: "white"; border.width: 3
    }

    MouseArea {
        anchors.fill: parent
        function pick(mx, my) {
            const dx = mx - wheel.cx, dy = wheel.cy - my
            const r = Math.hypot(dx, dy)
            if (r > wheel.radius + 12) return
            let hue = Math.atan2(dy, dx) / (2 * Math.PI)
            if (hue < 0) hue += 1
            wheel.picked(hue, Math.min(1, r / wheel.radius))
        }
        onPressed: (m) => pick(m.x, m.y)
        onPositionChanged: (m) => { if (pressed) pick(m.x, m.y) }
    }
}
