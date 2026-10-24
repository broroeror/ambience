#version 440
// Inner glow around the window's edge, coloured by up to 8 lights. Each light has an
// anchor point on the edge (where it sits in the room); a pixel takes the lights' colours
// weighted by how close it is to each anchor, and fades out with distance from the edge.
// Compile: /usr/lib/qt6/bin/qsb --glsl "100es,120,150" --hlsl 50 --msl 12 -o edgeglow.frag.qsb edgeglow.frag

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 size;          // item size, px
    float reach;        // how far the glow reaches in, px
    float strength;     // 0..1
    float spread;       // how far a light's colour runs along the edge, px
    vec4 c0; vec4 c1; vec4 c2; vec4 c3; vec4 c4; vec4 c5; vec4 c6; vec4 c7;   // rgb; a = in use
    vec2 p0; vec2 p1; vec2 p2; vec2 p3; vec2 p4; vec2 p5; vec2 p6; vec2 p7;   // anchors, 0..1
};

void lamp(vec4 c, vec2 p, vec2 pos, inout vec3 sum, inout float wsum) {
    vec2 d = pos - p * size;
    float w = c.a * exp(-dot(d, d) / (2.0 * spread * spread));
    sum += c.rgb * w;
    wsum += w;
}

void main() {
    vec2 pos = qt_TexCoord0 * size;
    float edge = min(min(pos.x, size.x - pos.x), min(pos.y, size.y - pos.y));
    float fall = 1.0 - clamp(edge / reach, 0.0, 1.0);
    fall = fall * fall * fall;
    if (fall <= 0.0) { fragColor = vec4(0.0); return; }

    vec3 sum = vec3(0.0);
    float wsum = 1e-6;
    lamp(c0, p0, pos, sum, wsum); lamp(c1, p1, pos, sum, wsum);
    lamp(c2, p2, pos, sum, wsum); lamp(c3, p3, pos, sum, wsum);
    lamp(c4, p4, pos, sum, wsum); lamp(c5, p5, pos, sum, wsum);
    lamp(c6, p6, pos, sum, wsum); lamp(c7, p7, pos, sum, wsum);
    vec3 col = sum / wsum;                      // the colour here, at its own brightness
    float level = max(col.r, max(col.g, col.b));
    vec3 hue = level > 0.0 ? col / level : vec3(0.0);
    float a = clamp(fall * strength * level, 0.0, 1.0);
    fragColor = vec4(hue * a, a) * qt_Opacity;   // premultiplied
}
