<script lang="ts">
	import { UI_FONT } from 'constants-shared/fonts';
	// Neon skin face for every bar button: glass disc + vector icon, with hover lift, press squash,
	// active pulse and (for the spin button) rotating arrows. Drawn around (x, y).
	import { onMount } from 'svelte';
	import { Tween } from 'svelte/motion';
	import { backOut, cubicOut } from 'svelte/easing';
	import { Container, Graphics, Text } from 'pixi-svelte';

	import { drawNeonBody, drawNeonIcon, lighten, uiSkin, type NeonIcon } from '../skin';

	const gothic = uiSkin.style === 'gothic';

	type Props = {
		x: number;
		y: number;
		size: number; // button diameter (pill: height)
		icon?: NeonIcon;
		label?: string; // pill mode: a wide capsule with this text instead of an icon
		pillWidth?: number;
		color: number;
		hovered?: boolean;
		pressed?: boolean;
		active?: boolean;
		disabled?: boolean;
		hero?: boolean; // the big spin button: filled body + idle rotation
		busy?: boolean; // reels running: arrows spin fast
	};

	const props: Props = $props();

	const scale = new Tween(1, { duration: 160, easing: backOut });
	const glow = new Tween(1, { duration: 200, easing: cubicOut });

	$effect(() => {
		scale.target = props.disabled ? 1 : props.pressed ? 0.88 : props.hovered ? 1.07 : 1;
		glow.target = props.disabled ? 0.2 : props.hovered || props.active ? 1.8 : 1;
	});

	// one clock drives the hero rotation and the active pulse
	let t = $state(0);
	let angle = $state(0);
	onMount(() => {
		let raf = 0;
		let last = performance.now();
		const tick = (now: number) => {
			const dt = Math.min(0.05, (now - last) / 1000);
			last = now;
			t += dt;
			if (props.hero) angle += dt * (props.busy ? 9 : 0.9);
			raf = requestAnimationFrame(tick);
		};
		raf = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(raf);
	});

	const r = $derived(props.size * 0.46);
	const pulse = $derived(props.active ? 0.5 + 0.5 * Math.sin(t * 5) : 0);
	const heroBreath = $derived(props.hero && !props.disabled ? 1 + 0.025 * Math.sin(t * 2.4) : 1);
</script>

<Container x={props.x} y={props.y} scale={scale.current * heroBreath} alpha={props.disabled ? 0.45 : 1}>
	{#if props.hero}
		<!-- rotating dashed halo behind the spin button -->
		<Graphics
			rotation={angle * 0.35}
			draw={(g) => {
				if (gothic) {
					// ring of carved rune diamonds instead of a neon dashed halo
					for (let i = 0; i < 16; i++) {
						const a = (i / 16) * Math.PI * 2;
						const cx = Math.cos(a) * r * 1.2, cy = Math.sin(a) * r * 1.2, d = r * (i % 4 === 0 ? 0.09 : 0.055);
						g.poly([cx, cy - d, cx + d, cy, cx, cy + d, cx - d, cy]).fill({ color: props.color, alpha: 0.7 });
					}
					return;
				}
				for (let i = 0; i < 12; i++) {
					const a = (i / 12) * Math.PI * 2;
					g.moveTo(Math.cos(a) * r * 1.2, Math.sin(a) * r * 1.2);
					g.arc(0, 0, r * 1.2, a, a + 0.28);
				}
				g.stroke({ width: r * 0.06, color: props.color, alpha: 0.75, cap: 'round' });
			}}
		/>
	{/if}
	{#if props.label !== undefined}
		{@const w = props.pillWidth ?? props.size * 2}
		{@const h = props.size}
		{@const breathe = props.disabled ? 0 : 0.5 + 0.5 * Math.sin(t * 3)}
		<Graphics
			draw={(g) => {
				const c = props.color;
				if (gothic) {
					// chamfered stone plaque, silver frame, coloured inlay that brightens on hover
					const plaque = (inset: number) => {
						const x0 = -w / 2 + inset, x1 = w / 2 - inset, y0 = -h / 2 + inset, y1 = h / 2 - inset, ch = h * 0.28;
						return [x0 + ch, y0, x1 - ch, y0, x1, y0 + ch, x1, y1 - ch, x1 - ch, y1, x0 + ch, y1, x0, y1 - ch, x0, y0 + ch];
					};
					g.poly(plaque(-h * 0.04).map((v, i) => (i % 2 ? v + h * 0.06 : v))).fill({ color: 0x000000, alpha: 0.45 });
					g.poly(plaque(0)).fill({ color: 0x24201f });
					g.poly(plaque(h * 0.1)).fill({ color: 0x15121a });
					g.poly(plaque(h * 0.1)).stroke({ width: h * 0.05, color: 0xb9bec2 });
					g.poly(plaque(h * 0.17)).stroke({
						width: h * 0.025,
						color: c,
						alpha: Math.min(1, 0.4 + 0.3 * breathe * glow.current),
					});
					return;
				}
				g.roundRect(-w / 2 - h * 0.1, -h / 2 - h * 0.1, w + h * 0.2, h * 1.2, h * 0.6).stroke({
					width: h * 0.16,
					color: c,
					alpha: 0.12 + 0.18 * breathe * glow.current,
				});
				g.roundRect(-w / 2, -h / 2, w, h, h / 2).fill({ color: 0x1a0d00, alpha: 0.92 });
				g.roundRect(-w / 2 + h * 0.08, -h / 2 + h * 0.08, w - h * 0.16, h * 0.42, h * 0.3).fill({
					color: c,
					alpha: 0.22,
				});
				g.roundRect(-w / 2, -h / 2, w, h, h / 2).stroke({ width: h * 0.09, color: c });
				g.roundRect(-w / 2 + h * 0.13, -h / 2 + h * 0.13, w - h * 0.26, h * 0.74, h * 0.37).stroke({
					width: h * 0.025,
					color: lighten(c, 0.6),
					alpha: 0.6,
				});
			}}
		/>
		<Text
			anchor={0.5}
			text={props.label}
			style={{
				fontFamily: UI_FONT,
				fontWeight: '900',
				fontSize: Math.min(h * 0.36, (w * 0.82) / Math.max(1, props.label.length * 0.62)),
				letterSpacing: h * 0.02,
				fill: lighten(props.color, 0.5),
				stroke: { color: gothic ? 0x050405 : 0x2a1200, width: h * 0.05 },
				dropShadow: gothic
					? { color: 0x000000, blur: h * 0.04, distance: h * 0.04, alpha: 0.8 }
					: { color: props.color, blur: h * 0.12, distance: 0, alpha: 0.9 },
			}}
		/>
	{:else}
		<Graphics
			draw={(g) =>
				drawNeonBody(g, r, props.color, { active: props.active, glow: glow.current + pulse, filled: props.hero })}
		/>
		<Graphics draw={(g) => drawNeonIcon(g, props.icon ?? 'menu', r * 0.5, props.hero ? 0xffffff : props.color, angle)} />
	{/if}
</Container>
