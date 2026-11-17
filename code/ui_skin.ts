import { UI_FONT } from 'constants-shared/fonts';
import type * as PIXI from 'pixi.js';
import { getContextApp } from 'pixi-svelte';

// Text colour per button when the game supplies a `ui_<key>` skin (see UiSprite.svelte).
// Keys are the UiSprite keys: button icons plus 'bet' and 'buyBonus'.
export const SKIN_TEXT: Record<string, number> = {
	menu: 0x7ffcff,
	menuExit: 0x7ffcff,
	payTable: 0x7ffcff,
	info: 0x7ffcff,
	settings: 0x7ffcff,
	soundOn: 0x7ffcff,
	soundOff: 0x7ffcff,
	bet: 0xff2ec4,
	turbo: 0xffb000,
	autoSpin: 0x3dff9a,
	buyBonus: 0xffd23f,
	decrease: 0xff4d6d,
	increase: 0x3da5ff,
};

// Neon skin: round glass buttons with vector icons drawn in code (crisp at any size, no button PNGs).
// A game opts in once at startup with setUiSkin({ neon: true }); other games keep the default boxes.
// style 'gothic' (Hexbound): carved stone medallions with silver rims and rivets, no glow; same icons.
export const uiSkin = { neon: false, style: 'neon' as 'neon' | 'gothic' };
const gothic = () => uiSkin.style === 'gothic';
// colors: per-button neon colour overrides (keys of SKIN_TEXT), so each game keeps its own palette
export const setUiSkin = (value: Partial<typeof uiSkin> & { colors?: Partial<typeof SKIN_TEXT> }) => {
	const { colors, ...rest } = value;
	Object.assign(uiSkin, rest);
	if (colors) Object.assign(SKIN_TEXT, colors);
};

// true when the game has loaded a skin for this key (or uses the neon skin); call during component init
export const createSkinCheck = () => {
	const app = getContextApp();
	return (key: string) => uiSkin.neon || !!app.stateApp.loadedAssets?.[`ui_${key}`];
};

// Skinned button text: sized so the longest word fits the button face, single symbols (+ / -) big,
// with a dark outline so it reads on the glass.
export const skinTextStyle = (text: string, baseSize: number, buttonWidth: number, fill: number) => {
	const longest = Math.max(...text.split(/\s+/).map((w) => w.length));
	const fontSize = longest <= 1 ? baseSize * 1.3 : Math.min(baseSize * 0.75, (buttonWidth * 0.88) / (longest * 0.62));
	return {
		align: 'center' as const,
		wordWrap: true,
		wordWrapWidth: buttonWidth * 0.9,
		fontFamily: UI_FONT,
		fontWeight: '800' as const,
		fontSize,
		fill,
		stroke: { color: 0x05020f, width: Math.max(3, fontSize * 0.14) },
	};
};

export type NeonIcon =
	| 'menu'
	| 'menuExit'
	| 'payTable'
	| 'info'
	| 'settings'
	| 'soundOn'
	| 'soundOff'
	| 'turbo'
	| 'autoSpin'
	| 'decrease'
	| 'increase'
	| 'spin'
	| 'stop';

// mix a colour toward white, t in 0..1
export const lighten = (c: number, t: number) => {
	const ch = (s: number) => Math.round(((c >> s) & 255) + (255 - ((c >> s) & 255)) * t);
	return (ch(16) << 16) | (ch(8) << 8) | ch(0);
};

// Draws one icon centred on (0,0); k is the icon half-size. The path is stroked twice: a wide faint
// pass for the neon bloom, then a thin bright core, so it reads like a lit tube rather than flat clip art.
export const drawNeonIcon = (g: PIXI.Graphics, icon: NeonIcon, k: number, color: number, spinAngle = 0) => {
	const core = lighten(color, 0.55);
	// gothic: a dark carved groove under a solid metal stroke instead of a neon bloom
	const passes = gothic()
		? [
				{ width: k * 0.34, color: 0x050405, alpha: 0.85 },
				{ width: k * 0.17, color: core, alpha: 1 },
			]
		: [
				{ width: k * 0.36, color, alpha: 0.28 },
				{ width: k * 0.17, color: core, alpha: 1 },
			];
	const line = (pts: number[][]) => {
		for (const p of passes) {
			g.moveTo(pts[0][0] * k, pts[0][1] * k);
			for (const [x, y] of pts.slice(1)) g.lineTo(x * k, y * k);
			g.stroke({ width: p.width, color: p.color, alpha: p.alpha, cap: 'round', join: 'round' });
		}
	};
	const arc = (r: number, a0: number, a1: number) => {
		for (const p of passes) {
			g.moveTo(Math.cos(a0) * r * k, Math.sin(a0) * r * k);
			g.arc(0, 0, r * k, a0, a1);
			g.stroke({ width: p.width, color: p.color, alpha: p.alpha, cap: 'round' });
		}
	};
	const fill = (pts: number[][]) => {
		g.poly(pts.flatMap(([x, y]) => [x * k, y * k])).fill(gothic() ? { color: 0x050405, alpha: 0.6 } : { color, alpha: 0.35 });
		g.poly(pts.flatMap(([x, y]) => [x * k, y * k])).stroke({ width: k * 0.12, color: core, join: 'round' });
		g.poly(pts.flatMap(([x, y]) => [x * k, y * k])).fill({ color: core, alpha: 0.9 });
	};
	// arrow head at angle a on a circle of radius r, pointing clockwise
	const arrowHead = (r: number, a: number, size: number) => {
		const x = Math.cos(a) * r, y = Math.sin(a) * r;
		const tx = -Math.sin(a), ty = Math.cos(a); // clockwise tangent
		const nx = Math.cos(a), ny = Math.sin(a);
		fill([
			[x + tx * size, y + ty * size],
			[x - nx * size * 0.75, y - ny * size * 0.75],
			[x + nx * size * 0.75, y + ny * size * 0.75],
		]);
	};
	const speaker = () =>
		fill([
			[-0.85, -0.3],
			[-0.45, -0.3],
			[-0.05, -0.7],
			[-0.05, 0.7],
			[-0.45, 0.3],
			[-0.85, 0.3],
		]);

	switch (icon) {
		case 'menu':
			for (const y of [-0.55, 0, 0.55]) line([[-0.75, y], [0.75, y]]);
			break;
		case 'menuExit':
			line([[-0.6, -0.6], [0.6, 0.6]]);
			line([[0.6, -0.6], [-0.6, 0.6]]);
			break;
		case 'payTable':
			for (const y of [-0.55, 0, 0.55]) {
				line([[-0.3, y], [0.8, y]]);
				g.circle(-0.7 * k, y * k, k * 0.13).fill({ color: core });
			}
			break;
		case 'info':
			g.circle(0, -0.62 * k, k * 0.17).fill({ color: core });
			line([[-0.22, -0.15], [0.05, -0.15], [0.05, 0.7]]);
			line([[-0.25, 0.7], [0.35, 0.7]]);
			break;
		case 'settings': {
			for (let i = 0; i < 8; i++) {
				const a = (i / 8) * Math.PI * 2;
				line([[Math.cos(a) * 0.55, Math.sin(a) * 0.55], [Math.cos(a) * 0.85, Math.sin(a) * 0.85]]);
			}
			arc(0.55, 0, Math.PI * 2);
			arc(0.2, 0, Math.PI * 2);
			break;
		}
		case 'soundOn':
			speaker();
			for (const r of [0.38, 0.7]) {
				for (const p of passes) {
					g.moveTo(Math.cos(-0.8) * r * k + 0.1 * k, Math.sin(-0.8) * r * k);
					g.arc(0.1 * k, 0, r * k, -0.8, 0.8);
					g.stroke({ width: p.width, color: p.color, alpha: p.alpha, cap: 'round' });
				}
			}
			break;
		case 'soundOff':
			speaker();
			line([[0.3, -0.3], [0.85, 0.3]]);
			line([[0.85, -0.3], [0.3, 0.3]]);
			break;
		case 'turbo':
			fill([
				[0.15, -0.95],
				[-0.55, 0.12],
				[-0.05, 0.12],
				[-0.2, 0.95],
				[0.55, -0.15],
				[0.05, -0.15],
			]);
			break;
		case 'autoSpin':
			arc(0.72, -Math.PI * 0.35, Math.PI * 1.25);
			arrowHead(0.72, Math.PI * 1.25, 0.3);
			fill([
				[-0.18, -0.32],
				[0.34, 0],
				[-0.18, 0.32],
			]);
			break;
		case 'decrease':
			line([[-0.6, 0], [0.6, 0]]);
			break;
		case 'increase':
			line([[-0.6, 0], [0.6, 0]]);
			line([[0, -0.6], [0, 0.6]]);
			break;
		case 'spin': {
			// two chasing arrows, rotated by spinAngle
			for (const off of [0, Math.PI]) {
				const a0 = spinAngle + off + 0.35;
				const a1 = spinAngle + off + Math.PI - 0.45;
				arc(0.68, a0, a1);
				arrowHead(0.68, a1, 0.32);
			}
			break;
		}
		case 'stop':
			g.roundRect(-0.48 * k, -0.48 * k, 0.96 * k, 0.96 * k, k * 0.14).fill({ color: core });
			g.roundRect(-0.48 * k, -0.48 * k, 0.96 * k, 0.96 * k, k * 0.14).stroke({
				width: k * 0.3,
				color,
				alpha: 0.3,
			});
			break;
	}
};

// Round glass button body: bloom ring, dark glass, bright rim, top glare.
export const drawNeonBody = (
	g: PIXI.Graphics,
	r: number,
	color: number,
	opts: { active?: boolean; glow?: number; filled?: boolean } = {},
) => {
	const glow = opts.glow ?? 1;
	if (gothic()) return drawGothicBody(g, r, color, opts.active, glow, opts.filled);
	g.circle(0, 0, r * 1.08).stroke({ width: r * 0.22, color, alpha: 0.16 * glow });
	g.circle(0, 0, r).fill({ color: opts.filled ? color : 0x0a0420, alpha: opts.filled ? 0.9 : 0.88 });
	if (opts.filled) g.circle(0, 0, r * 0.8).fill({ color: 0x14052e, alpha: 0.55 });
	if (opts.active) g.circle(0, 0, r * 0.94).fill({ color, alpha: 0.28 });
	g.circle(0, 0, r).stroke({ width: r * 0.1, color, alpha: 1 });
	g.circle(0, 0, r * 0.86).stroke({ width: r * 0.03, color: lighten(color, 0.6), alpha: 0.5 });
	// glare on the upper-left of the glass
	g.moveTo(Math.cos(Math.PI * 1.1) * r * 0.72, Math.sin(Math.PI * 1.1) * r * 0.72);
	g.arc(0, 0, r * 0.72, Math.PI * 1.1, Math.PI * 1.45);
	g.stroke({ width: r * 0.07, color: 0xffffff, alpha: 0.35, cap: 'round' });
};

// Gothic medallion: iron outer ring with rivets, carved stone face, silver bevel, thin coloured inlay.
// glow only brightens the inlay (hover / active), so the stone itself never lights up like neon.
const drawGothicBody = (g: PIXI.Graphics, r: number, color: number, active = false, glow = 1, filled = false) => {
	const silver = 0xb9bec2;
	g.circle(0, r * 0.06, r * 1.04).fill({ color: 0x000000, alpha: 0.45 }); // drop shadow
	g.circle(0, 0, r).fill({ color: 0x24201f });
	g.circle(0, 0, r).stroke({ width: r * 0.05, color: 0x0b090a });
	for (let i = 0; i < 8; i++) {
		const a = (i / 8) * Math.PI * 2 + Math.PI / 8;
		g.circle(Math.cos(a) * r * 0.9, Math.sin(a) * r * 0.9, r * 0.045).fill({ color: silver, alpha: 0.85 });
	}
	g.circle(0, 0, r * 0.8).fill({ color: filled ? 0x0f2a1c : 0x15121a });
	if (filled) g.circle(0, 0, r * 0.8).fill({ color, alpha: 0.18 });
	if (active) g.circle(0, 0, r * 0.8).fill({ color, alpha: 0.2 });
	g.circle(0, 0, r * 0.8).stroke({ width: r * 0.06, color: silver });
	g.circle(0, 0, r * 0.72).stroke({ width: r * 0.025, color, alpha: Math.min(1, 0.45 * glow) });
	// cold highlight on the upper bevel
	g.moveTo(Math.cos(Math.PI * 1.15) * r * 0.8, Math.sin(Math.PI * 1.15) * r * 0.8);
	g.arc(0, 0, r * 0.8, Math.PI * 1.15, Math.PI * 1.6);
	g.stroke({ width: r * 0.03, color: 0xffffff, alpha: 0.45, cap: 'round' });
};
