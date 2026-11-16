import {
	Body, Button as EmailButton, Column, Container, Head, Hr, Html, Img, Link, Preview, Row, Section, Text,
} from "@react-email/components";
import type { CSSProperties, ReactNode } from "react";
import { type Address, type Brand, type Item, type Order, type Step, imageUrl, money, orderTotals, t } from "./data";

export type Layout = "classic" | "lookbook";

const text: CSSProperties = { margin: 0, fontFamily: t.font, letterSpacing: "0.005em" };

export const s = {
	muted: { ...text, fontSize: 12, color: t.inkGray5, lineHeight: "1.4" },
	label: { ...text, fontSize: 12, color: t.inkGray5, marginBottom: 6 },
	para: { ...text, fontSize: 14, lineHeight: "1.55", color: t.inkGray7 },
	strong: { color: t.inkGray9, fontWeight: t.medium },
	address: { ...text, fontSize: 13, lineHeight: "1.55", color: t.inkGray7 },
	sectionTitle: { ...text, fontSize: 15, fontWeight: t.semibold, color: t.inkGray9, marginBottom: 8 },
	h2: { ...text, fontSize: 17, fontWeight: t.semibold, color: t.inkGray9, marginBottom: 14 },
	kicker: { ...text, fontSize: 13, color: t.inkGray5 },
	line: { ...text, fontSize: 14, color: t.inkGray7, lineHeight: "1.9" },
	hr: { borderColor: t.outlineGray2, margin: "14px 0" },
	half: { width: "50%", verticalAlign: "top", paddingRight: 12 },
	num: { fontVariantNumeric: "tabular-nums" },
} satisfies Record<string, CSSProperties>;

const layouts = {
	classic: {
		body: { backgroundColor: t.surfaceGray1, margin: 0, padding: "32px 12px", fontFamily: t.font },
		container: { maxWidth: 600, width: "100%", margin: "0 auto", padding: 0 },
		heading: { ...text, fontSize: 26, lineHeight: "1.15", fontWeight: t.semibold, letterSpacing: "-0.02em", color: t.inkGray9 },
		intro: { ...text, marginTop: 10, fontSize: 14, lineHeight: "1.55", color: t.inkGray7 },
	},
	lookbook: {
		body: { backgroundColor: t.surfaceBase, margin: 0, padding: "40px 20px", fontFamily: t.font },
		container: { maxWidth: 560, width: "100%", margin: "0 auto", padding: 0 },
		heading: { ...text, marginTop: 10, fontSize: 34, lineHeight: "1.08", fontWeight: t.semibold, letterSpacing: "-0.025em", color: t.inkGray9 },
		intro: { ...text, marginTop: 14, fontSize: 15, lineHeight: "1.55", color: t.inkGray7 },
	},
} satisfies Record<Layout, Record<string, CSSProperties>>;

export function EmailLayout({ layout, preview, children }: { layout: Layout; preview: string; children: ReactNode }) {
	return (
		<Html lang="en">
			<Head>
				<link href={t.fontStylesheet} rel="stylesheet" />
			</Head>
			<Preview>{preview}</Preview>
			<Body style={layouts[layout].body}>
				<Container style={layouts[layout].container}>{children}</Container>
			</Body>
		</Html>
	);
}

export function Header({ brand, layout, meta }: { brand: Brand; layout: Layout; meta?: string }) {
	if (layout === "lookbook") {
		return <Text style={{ ...text, fontSize: 15, fontWeight: t.semibold, color: t.inkGray9, marginBottom: 40 }}>{brand.name}</Text>;
	}
	return (
		<Row style={{ padding: "8px 4px 20px" }}>
			<Column>
				<Text style={{ ...text, fontSize: 16, fontWeight: t.semibold, color: t.inkGray9, lineHeight: "28px" }}>
					{brand.logo ? (
						<Img src={brand.logo} height="26" alt={brand.name} style={{ display: "inline-block", verticalAlign: "middle", marginRight: 10 }} />
					) : (
						<span style={markStyle}>{brand.name[0]}</span>
					)}
					{brand.name}
				</Text>
			</Column>
			{meta && (
				<Column align="right">
					<Text style={s.muted}>{meta}</Text>
				</Column>
			)}
		</Row>
	);
}

const markStyle: CSSProperties = {
	display: "inline-block", width: 26, height: 26, lineHeight: "26px", textAlign: "center",
	backgroundColor: t.inkGray9, color: t.inkWhite, borderRadius: t.radiusThumb, fontSize: 14, fontWeight: 700, marginRight: 10,
};

export function Heading({ layout, children }: { layout: Layout; children: ReactNode }) {
	return <Text style={layouts[layout].heading}>{children}</Text>;
}

export function Intro({ layout, children }: { layout: Layout; children: ReactNode }) {
	return <Text style={layouts[layout].intro}>{children}</Text>;
}

export function Card({ children, first, padding }: { children: ReactNode; first?: boolean; padding?: string }) {
	return (
		<Section
			style={{
				backgroundColor: t.surfaceBase, borderRadius: t.radiusCard, border: `1px solid ${t.outlineGray1}`,
				padding: padding ?? (first ? "28px" : "24px 28px"), marginTop: first ? 0 : 12,
			}}
		>
			{children}
		</Section>
	);
}

export function Button({ href, children, layout = "classic", marginTop }: { href: string; children: ReactNode; layout?: Layout; marginTop?: number }) {
	return (
		<EmailButton
			href={href}
			style={{
				marginTop: marginTop ?? (layout === "classic" ? 24 : 12), backgroundColor: t.inkGray9, color: t.inkWhite,
				fontFamily: t.font, fontSize: 14, fontWeight: t.medium, borderRadius: t.radiusThumb, textDecoration: "none",
				padding: layout === "classic" ? "11px 18px" : "12px 20px",
			}}
		>
			{children}
		</EmailButton>
	);
}

type PlaceholderTileProps = { name: string; width: number | string; height: number; fontSize?: number; margin?: string };

export function PlaceholderTile({ name, width, height, fontSize = 16, margin = "0" }: PlaceholderTileProps) {
	return (
		<div
			style={{
				width, height, margin, lineHeight: `${height}px`, textAlign: "center", borderRadius: t.radiusThumb,
				backgroundColor: t.surfaceGray2, color: t.inkGray5, fontSize, fontFamily: t.font,
			}}
		>
			{name[0]}
		</div>
	);
}

export function ProgressSteps({ steps, layout }: { steps: Step[]; layout: Layout }) {
	if (layout === "lookbook") {
		return (
			<>
				{steps.map((step, index) => (
					<Row key={step.title}>
						<Column style={{ width: 24, verticalAlign: "top" }}>
							<div
								style={{
									width: 8, height: 8, borderRadius: "50%", border: "2px solid", marginTop: 3,
									backgroundColor: step.done ? t.inkGreen6 : t.surfaceBase, borderColor: step.done ? t.inkGreen6 : t.inkGray3,
								}}
							/>
							{index < steps.length - 1 && (
								<div style={{ width: 2, height: 20, backgroundColor: t.outlineGray2, marginLeft: 5, marginTop: 4 }} />
							)}
						</Column>
						<Column style={{ verticalAlign: "top", paddingBottom: 12 }}>
							<Text style={{ ...text, fontSize: 14, fontWeight: t.medium, lineHeight: "1.3", color: step.done ? t.inkGray9 : t.inkGray5 }}>
								{step.title} <span style={{ fontWeight: t.regular, color: t.inkGray5, marginLeft: 6 }}>{step.hint}</span>
							</Text>
						</Column>
					</Row>
				))}
			</>
		);
	}
	return (
		<Row style={{ marginTop: 22 }}>
			{steps.map((step, index) => (
				<Column
					key={step.title}
					style={{
						borderTop: "3px solid", borderTopColor: step.done ? t.inkGreen6 : t.outlineGray2, paddingTop: 10,
						verticalAlign: "top", width: `${100 / steps.length}%`, paddingRight: index < steps.length - 1 ? 8 : 0,
					}}
				>
					<Text style={{ ...text, fontSize: 13, fontWeight: t.medium, lineHeight: "1.3", color: step.done ? t.inkGray9 : t.inkGray5 }}>{step.title}</Text>
					<Text style={{ ...text, fontSize: 12, color: t.inkGray5, lineHeight: "1.4", marginTop: 2 }}>{step.hint}</Text>
				</Column>
			))}
		</Row>
	);
}

const onSale = (row: Item) => row.price_list_rate > row.rate;

export function ItemRow({ row, imageBase }: { row: Item; imageBase: string }) {
	const thumb = imageUrl(imageBase, row.image, "thumb");
	const thumbStyle: CSSProperties = { display: "block", borderRadius: t.radiusThumb, backgroundColor: t.surfaceGray2, margin: "12px 0" };
	return (
		<Row style={{ borderBottom: `1px solid ${t.outlineGray1}` }}>
			<Column style={{ width: 64, verticalAlign: "top" }}>
				{thumb ? (
					<Img src={thumb} width="52" height="64" alt="" style={thumbStyle} />
				) : (
					<PlaceholderTile name={row.item_name} width={52} height={64} margin="12px 0" />
				)}
			</Column>
			<Column style={{ verticalAlign: "top" }}>
				<Text style={{ ...text, fontSize: 14, fontWeight: t.medium, color: t.inkGray9, lineHeight: "1.3", marginTop: 14 }}>{row.item_name}</Text>
				<Text style={{ ...text, fontSize: 13, color: t.inkGray5, lineHeight: "1.4", marginTop: 3 }}>
					{row.variant}, qty <span style={s.num}>{row.qty}</span>
					{onSale(row) && <span style={{ color: t.inkGreen6, fontWeight: t.medium }}> Sale</span>}
				</Text>
			</Column>
			<Column align="right" style={{ verticalAlign: "top", width: 110 }}>
				<Text style={{ ...text, ...s.num, fontSize: 14, fontWeight: t.medium, color: t.inkGray9, marginTop: 14 }}>{money(row.qty * row.rate)}</Text>
				{onSale(row) && (
					<Text style={{ ...text, ...s.num, fontSize: 12, color: t.inkGray5, textDecoration: "line-through", marginTop: 3 }}>
						{money(row.qty * row.price_list_rate)}
					</Text>
				)}
			</Column>
		</Row>
	);
}

export function ItemCard({ row, imageBase }: { row: Item; imageBase: string }) {
	const photo = imageUrl(imageBase, row.image, "card");
	return (
		<>
			{photo ? (
				<Img
					src={photo}
					alt={row.item_name}
					width="272"
					height="240"
					style={{
						display: "block", width: "100%", height: 240, objectFit: "cover", objectPosition: "50% 25%",
						borderRadius: t.radiusThumb, backgroundColor: t.surfaceGray2,
					}}
				/>
			) : (
				<PlaceholderTile name={row.item_name} width="100%" height={240} fontSize={24} />
			)}
			<Text style={{ ...text, marginTop: 12, fontSize: 14, fontWeight: t.medium, lineHeight: "1.3", color: t.inkGray9 }}>{row.item_name}</Text>
			<Text style={{ ...text, marginTop: 3, fontSize: 13, color: t.inkGray5 }}>
				{row.variant}
				{row.qty > 1 ? `, ${row.qty} pieces` : ""}
			</Text>
			<Text style={{ ...text, ...s.num, marginTop: 6, fontSize: 14, fontWeight: t.medium, color: t.inkGray9 }}>
				{money(row.qty * row.rate)}
				{onSale(row) && (
					<span style={{ marginLeft: 8, fontSize: 13, fontWeight: t.regular, color: t.inkGray5, textDecoration: "line-through" }}>
						{money(row.qty * row.price_list_rate)}
					</span>
				)}
			</Text>
		</>
	);
}

export function ItemGrid({ items, imageBase }: { items: Item[]; imageBase: string }) {
	const pairs: Item[][] = [];
	for (let index = 0; index < items.length; index += 2) pairs.push(items.slice(index, index + 2));
	return (
		<Section style={{ marginTop: 28 }}>
			{pairs.map((pair) => (
				<Row key={pair[0].item_code} style={{ marginBottom: 24 }}>
					{pair.map((row, position) => (
						<Column
							key={row.item_code}
							style={{ width: "50%", verticalAlign: "top", paddingLeft: position ? 8 : 0, paddingRight: position ? 0 : 8 }}
						>
							<ItemCard row={row} imageBase={imageBase} />
						</Column>
					))}
					{pair.length === 1 && <Column style={{ width: "50%" }} />}
				</Row>
			))}
		</Section>
	);
}

export function Line({ label, value, color }: { label: string; value: string; color?: string }) {
	return (
		<Row>
			<Column>
				<Text style={s.line}>{label}</Text>
			</Column>
			<Column align="right">
				<Text style={{ ...s.line, ...s.num, color: color ?? t.inkGray9 }}>{value}</Text>
			</Column>
		</Row>
	);
}

function ChargeLines({ order, subtotal }: { order: Order; subtotal: number }) {
	return (
		<>
			<Line label="Subtotal" value={money(subtotal)} />
			{order.discount_amount > 0 && (
				<Line
					label={order.coupon_code ? `Discount (${order.coupon_code})` : "Discount"}
					value={`−${money(order.discount_amount)}`}
					color={t.inkGreen6}
				/>
			)}
			{order.charges.map((charge) => (
				<Line key={charge.description} label={charge.description} value={charge.amount ? money(charge.amount) : "Free"} />
			))}
		</>
	);
}

export function Totals({ order, layout, totalLabel = "Total" }: { order: Order; layout: Layout; totalLabel?: string }) {
	const { subtotal, grand, tax } = orderTotals(order);
	const taxNote = `Includes ${money(tax)} ${order.tax_label}`;
	if (layout === "lookbook") {
		return (
			<Section style={{ backgroundColor: t.surfaceGray2, borderRadius: t.radiusCard, padding: "20px 24px 18px", marginTop: 8 }}>
				<ChargeLines order={order} subtotal={subtotal} />
				<Hr style={{ ...s.hr, margin: "12px 0" }} />
				<Row>
					<Column style={{ verticalAlign: "bottom" }}>
						<Text style={{ ...text, fontSize: 13, color: t.inkGray5 }}>Paid with {order.payment_method}</Text>
					</Column>
					<Column align="right">
						<Text style={{ ...text, ...s.num, fontSize: 24, fontWeight: t.semibold, letterSpacing: "-0.015em", color: t.inkGray9 }}>{money(grand)}</Text>
					</Column>
				</Row>
				<Text style={{ ...s.muted, ...s.num, textAlign: "right", marginTop: 4 }}>{taxNote}</Text>
			</Section>
		);
	}
	return (
		<>
			<Hr style={s.hr} />
			<ChargeLines order={order} subtotal={subtotal} />
			<Hr style={s.hr} />
			<Row>
				<Column>
					<Text style={{ ...text, fontSize: 15, fontWeight: t.semibold, color: t.inkGray9 }}>{totalLabel}</Text>
				</Column>
				<Column align="right">
					<Text style={{ ...text, ...s.num, fontSize: 20, fontWeight: t.semibold, color: t.inkGray9, letterSpacing: "-0.01em" }}>{money(grand)}</Text>
				</Column>
			</Row>
			<Text style={{ ...s.muted, ...s.num, textAlign: "right", marginTop: 2 }}>{taxNote}</Text>
		</>
	);
}

type AddressBlockProps = {
	label: string;
	address?: Address | null;
	emptyText?: string;
	extraLines?: (string | null | undefined)[];
	bold?: boolean;
};

export function AddressBlock({ label, address, emptyText, extraLines = [], bold = true }: AddressBlockProps) {
	const extras = extraLines.filter(Boolean) as string[];
	if (!address && !emptyText) return null;
	return (
		<>
			<Text style={s.label}>{label}</Text>
			<Text style={s.address}>
				{address ? (
					<>
						{bold ? <b style={s.strong}>{address.name}</b> : address.name}
						{address.lines.map((line) => (
							<span key={line}>
								<br />
								{line}
							</span>
						))}
					</>
				) : (
					emptyText
				)}
				{extras.map((line) => (
					<span key={line}>
						<br />
						{line}
					</span>
				))}
			</Text>
		</>
	);
}

export function FactBlock({ label, title, detail }: { label: string; title: string; detail?: string }) {
	return (
		<>
			<Text style={s.label}>{label}</Text>
			<Text style={s.address}>
				<b style={s.strong}>{title}</b>
				{detail && (
					<>
						<br />
						{detail}
					</>
				)}
			</Text>
		</>
	);
}

export function NoteBlock({ label, body, first = true }: { label: string; body?: string; first?: boolean }) {
	if (!body) return null;
	return (
		<>
			<Text style={{ ...s.label, marginTop: first ? 0 : 16 }}>{label}</Text>
			<Text style={s.para}>{body}</Text>
		</>
	);
}

type FooterProps = {
	brand: Brand;
	closing?: string;
	reason: string;
	links?: { label: string; url: string }[];
	layout?: Layout;
};

export function Footer({ brand, closing, reason, links = brand.footer_links, layout = "classic" }: FooterProps) {
	return (
		<Section style={{ padding: layout === "classic" ? `${closing ? 8 : 20}px 4px 0` : 0 }}>
			{closing && <Text style={{ ...s.para, marginBottom: 16 }}>{closing}</Text>}
			{links.length > 0 && (
				<Text style={{ ...s.muted, marginBottom: 8 }}>
					{links.map((link, index) => (
						<Link key={link.label} href={link.url} style={{ color: t.inkGray7, textDecoration: "underline", marginLeft: index ? 16 : 0 }}>
							{link.label}
						</Link>
					))}
				</Text>
			)}
			<Text style={{ ...s.muted, lineHeight: "1.5" }}>
				{brand.legal_name}, {brand.address}. GSTIN {brand.tax_id}.
				<br />
				{reason}
			</Text>
		</Section>
	);
}
