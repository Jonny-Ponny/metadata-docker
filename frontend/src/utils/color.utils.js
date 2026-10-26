// src/utils/color.utils.js

// HSL helpers
function hexToHsl(hex) {
  let r = parseInt(hex.slice(1, 3), 16) / 255;
  let g = parseInt(hex.slice(3, 5), 16) / 255;
  let b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b),
    min = Math.min(r, g, b);
  let h,
    s,
    l = (max + min) / 2;
  if (max === min) {
    h = s = 0;
  } else {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r:
        h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
        break;
      case g:
        h = ((b - r) / d + 2) / 6;
        break;
      case b:
        h = ((r - g) / d + 4) / 6;
        break;
    }
  }
  return { h, s, l };
}

function hslToHex(h, s, l) {
  let r, g, b;
  if (s === 0) {
    r = g = b = l;
  } else {
    const hue2rgb = (p, q, t) => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }
  return (
    "#" +
    [r, g, b]
      .map((c) =>
        Math.round(c * 255)
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
  );
}

function adjustLightness(hex, deltaL, deltaS = 0) {
  const { h, s, l } = hexToHsl(hex);
  const newL = Math.min(1, Math.max(0, l + deltaL));
  const newS = Math.min(1, Math.max(0, s + deltaS));
  return hslToHex(h, newS, newL);
}

// Derivation constants
const FOCUS_LIGHTEN = 0.08; // light mode focus: slightly lighter
const FOCUS_SATURATE = 0.25; // more saturated
const DARK_LIGHTEN = 0.1; // dark mode main: lighter
const FOCUS_DARK_LIGHTEN = 0.2; // dark mode focus: lighter

// Generate full theme
export function generateFullTheme(colors) {
  const {
    "color-primary": primary,
    "color-badge-audio": badgeAudio,
    "color-badge-image": badgeImage,
    "color-badge-text": badgeText,
  } = colors;

  // Derive all variants
  const primaryFocus = adjustLightness(primary, FOCUS_LIGHTEN, FOCUS_SATURATE);
  const primaryDark = adjustLightness(primary, DARK_LIGHTEN, 0);
  const primaryFocusDark = adjustLightness(primary, FOCUS_DARK_LIGHTEN, 0);

  const badgeAudioDark = adjustLightness(badgeAudio, DARK_LIGHTEN, 0);
  const badgeImageDark = adjustLightness(badgeImage, DARK_LIGHTEN, 0);
  const badgeTextDark = adjustLightness(badgeText, DARK_LIGHTEN, 0);

  const alpha = (hex, a) => hex + a;

  return {
    "--color-primary": primary,
    "--color-primary-focus": primaryFocus,
    "--color-primary-dark": primaryDark,
    "--color-primary-dark-focus": primaryFocusDark,
    "--color-primary-transparent": alpha(primary, "40"),
    "--color-primary-transparent-dark": alpha(primaryDark, "30"),
    "--color-lrc-playing-transparent": alpha(primary, "0d"),

    "--color-badge-audio": badgeAudio,
    "--color-badge-audio-dark": badgeAudioDark,
    "--color-badge-audio-background": alpha(badgeAudio, "40"),
    "--color-badge-audio-background-dark": alpha(badgeAudioDark, "30"),

    "--color-badge-image": badgeImage,
    "--color-badge-image-dark": badgeImageDark,
    "--color-badge-image-background": alpha(badgeImage, "26"),
    "--color-badge-image-background-dark": alpha(badgeImageDark, "33"),

    "--color-badge-text": badgeText,
    "--color-badge-text-dark": badgeTextDark,
    "--color-badge-text-background": alpha(badgeText, "26"),
    "--color-badge-text-background-dark": alpha(badgeTextDark, "33"),
  };
}
