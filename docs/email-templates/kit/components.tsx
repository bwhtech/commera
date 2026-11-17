import {
	Body,
	Button as EmailButton,
	Column,
	Container,
	Head,
	Hr,
	Html,
	Img,
	Link,
	Preview,
	Row,
	Section,
	Text,
} from '@react-email/components';
import {
	type CSSProperties,
	Children,
	type ReactNode,
	createContext,
	useContext,
} from 'react';
import {
	type Address,
	type Brand,
	type Item,
	type Order,
	type Sample,
	type Step,
	imageUrl,
	money,
	orderTotals,
	t,
} from './data';

type Layout = 'classic' | 'lookbook';

const LayoutContext = createContext<Layout>('classic');

const text: CSSProperties = {
	margin: 0,
	fontFamily: t.font,
	letterSpacing: '0.005em',
};
const title: CSSProperties = {
	...text,
	fontSize: 15,
	fontWeight: t.semibold,
	color: t.inkGray9,
};
const num: CSSProperties = { fontVariantNumeric: 'tabular-nums' };

export const s = {
	muted: { ...text, fontSize: 12, color: t.inkGray5, lineHeight: '1.4' },
	caption: { ...text, fontSize: 13, color: t.inkGray5 },
	label: { ...text, fontSize: 12, color: t.inkGray5, marginBottom: 6 },
	para: { ...text, fontSize: 14, lineHeight: '1.55', color: t.inkGray7 },
	value: { ...text, fontSize: 14, fontWeight: t.medium, color: t.inkGray9 },
	strong: { color: t.inkGray9, fontWeight: t.medium },
	address: { ...text, fontSize: 13, lineHeight: '1.55', color: t.inkGray7 },
	title,
	sectionTitle: { ...title, marginBottom: 8 },
	line: { ...text, fontSize: 14, color: t.inkGray7, lineHeight: '1.9' },
	hr: { borderColor: t.outlineGray2, margin: '14px 0' },
	half: { width: '50%', verticalAlign: 'top', paddingRight: 12 },
	num,
	amount: { ...title, ...num, fontSize: 20, letterSpacing: '-0.01em' },
} satisfies Record<string, CSSProperties>;

const layouts = {
	classic: {
		background: t.surfaceGray1,
		padding: '32px 12px',
		maxWidth: 600,
		heading: {
			...title,
			fontSize: 26,
			lineHeight: '1.15',
			letterSpacing: '-0.02em',
		},
		intro: { ...s.para, marginTop: 10 },
	},
	lookbook: {
		background: t.surfaceBase,
		padding: '40px 20px',
		maxWidth: 560,
		heading: {
			...title,
			marginTop: 10,
			fontSize: 34,
			lineHeight: '1.08',
			letterSpacing: '-0.025em',
		},
		intro: { ...s.para, marginTop: 14, fontSize: 15 },
	},
};

export function EmailLayout({
	layout = 'classic',
	preview,
	children,
}: { layout?: Layout; preview: string; children: ReactNode }) {
	const { background, padding, maxWidth } = layouts[layout];
	return (
		<LayoutContext.Provider value={layout}>
			<Html lang="en">
				<Head>
					<link href={t.fontStylesheet} rel="stylesheet" />
				</Head>
				<Preview>{preview}</Preview>
				<Body
					style={{
						backgroundColor: background,
						margin: 0,
						padding,
						fontFamily: t.font,
					}}
				>
					<Container
						style={{ maxWidth, width: '100%', margin: '0 auto', padding: 0 }}
					>
						{children}
					</Container>
				</Body>
			</Html>
		</LayoutContext.Provider>
	);
}

export function Header({ brand, meta }: { brand: Brand; meta?: string }) {
	if (useContext(LayoutContext) === 'lookbook') {
		return <Text style={{ ...title, marginBottom: 40 }}>{brand.name}</Text>;
	}
	return (
		<Row style={{ padding: '8px 4px 20px' }}>
			<Column>
				<Text style={{ ...title, fontSize: 16, lineHeight: '28px' }}>
					{brand.logo ? (
						<Img
							src={brand.logo}
							height="26"
							alt={brand.name}
							style={{
								display: 'inline-block',
								verticalAlign: 'middle',
								marginRight: 10,
							}}
						/>
					) : (
						<span
							style={{
								display: 'inline-block',
								width: 26,
								height: 26,
								lineHeight: '26px',
								textAlign: 'center',
								backgroundColor: t.inkGray9,
								color: t.inkWhite,
								borderRadius: t.radiusThumb,
								fontSize: 14,
								fontWeight: 700,
								marginRight: 10,
							}}
						>
							{brand.name[0]}
						</span>
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

export function Heading({ children }: { children: ReactNode }) {
	return (
		<Text style={layouts[useContext(LayoutContext)].heading}>{children}</Text>
	);
}

export function Intro({ children }: { children: ReactNode }) {
	return (
		<Text style={layouts[useContext(LayoutContext)].intro}>{children}</Text>
	);
}

export function Card({
	children,
	first,
}: { children: ReactNode; first?: boolean }) {
	return (
		<Section
			style={{
				backgroundColor: t.surfaceBase,
				borderRadius: t.radiusCard,
				border: `1px solid ${t.outlineGray1}`,
				padding: first ? '28px' : '24px 28px',
				marginTop: first ? 0 : 12,
			}}
		>
			{children}
		</Section>
	);
}

export function Button({
	href,
	children,
	marginTop = 24,
}: { href: string; children: ReactNode; marginTop?: number }) {
	const classic = useContext(LayoutContext) === 'classic';
	return (
		<EmailButton
			href={href}
			style={{
				marginTop,
				backgroundColor: t.inkGray9,
				color: t.inkWhite,
				fontFamily: t.font,
				fontSize: 14,
				fontWeight: t.medium,
				borderRadius: t.radiusThumb,
				textDecoration: 'none',
				padding: classic ? '11px 18px' : '12px 20px',
			}}
		>
			{children}
		</EmailButton>
	);
}

export function Panel({
	children,
	marginTop = 22,
	padding = '16px 20px',
}: { children: ReactNode; marginTop?: number; padding?: string }) {
	return (
		<Section
			style={{
				backgroundColor: t.surfaceGray2,
				borderRadius: t.radiusCard,
				padding,
				marginTop,
			}}
		>
			{children}
		</Section>
	);
}

export function AmountPanel({
	label,
	amount,
	amountStyle,
	children,
}: {
	label: string;
	amount: string;
	amountStyle?: CSSProperties;
	children: ReactNode;
}) {
	return (
		<Panel>
			<Text style={s.label}>{label}</Text>
			<Text style={{ ...s.amount, ...amountStyle }}>{amount}</Text>
			<Text style={{ ...s.address, marginTop: 6 }}>{children}</Text>
		</Panel>
	);
}

export function TwoColumns({
	children,
	marginTop,
}: { children: ReactNode; marginTop?: number }) {
	return (
		<Row style={{ marginTop }}>
			{Children.map(children, (child) => (
				<Column style={s.half}>{child}</Column>
			))}
		</Row>
	);
}

export function ShipmentPanel({
	shipment,
	marginTop,
}: { shipment: Sample['shipment']; marginTop?: number }) {
	return (
		<Panel marginTop={marginTop}>
			<TwoColumns>
				<FactBlock label="Carrier" title={shipment.carrier} />
				<FactBlock label="Tracking number" title={shipment.tracking_number} />
			</TwoColumns>
		</Panel>
	);
}

export function PlaceholderTile({
	name,
	width,
	height,
	fontSize = 16,
	margin = '0',
}: {
	name: string;
	width: number | string;
	height: number;
	fontSize?: number;
	margin?: string;
}) {
	return (
		<div
			style={{
				width,
				height,
				margin,
				lineHeight: `${height}px`,
				textAlign: 'center',
				borderRadius: t.radiusThumb,
				backgroundColor: t.surfaceGray2,
				color: t.inkGray5,
				fontSize,
				fontFamily: t.font,
			}}
		>
			{name[0]}
		</div>
	);
}

function stepStatus(steps: Step[]) {
	const current = [...steps].reverse().find((step) => step.done) ?? steps[0];
	const upcoming = steps
		.slice(steps.indexOf(current) + 1)
		.find((step) => step.date);
	const when = upcoming
		? `${upcoming.pending_title ?? upcoming.title} ${upcoming.date}`
		: current.date ?? '';
	return { title: current.title, when, detail: current.detail };
}

export function ProgressSteps({
	steps,
	marginTop = 24,
	detail,
}: { steps: Step[]; marginTop?: number; detail?: string }) {
	const status = stepStatus(steps);
	const statusDetail = detail ?? status.detail;
	return (
		<Section style={{ marginTop }}>
			<Row>
				<Column style={{ verticalAlign: 'bottom' }}>
					<Text style={{ ...title, lineHeight: '1.3' }}>{status.title}</Text>
				</Column>
				<Column
					align="right"
					style={{ verticalAlign: 'bottom', whiteSpace: 'nowrap' }}
				>
					<Text style={{ ...s.caption, ...num, lineHeight: '1.3' }}>
						{status.when}
					</Text>
				</Column>
			</Row>
			<Row style={{ marginTop: 10 }}>
				{steps.map((step, index) => (
					<Column
						key={step.title}
						style={{
							width: `${100 / steps.length}%`,
							padding: 0,
							paddingRight: index < steps.length - 1 ? 4 : 0,
							verticalAlign: 'top',
						}}
					>
						<div
							style={{
								height: 4,
								lineHeight: '4px',
								fontSize: 1,
								borderRadius: 4,
								backgroundColor: step.done ? t.inkGreen6 : t.outlineGray2,
							}}
						>
							&nbsp;
						</div>
					</Column>
				))}
			</Row>
			{statusDetail && (
				<Text style={{ ...s.caption, lineHeight: '1.4', marginTop: 8 }}>
					{statusDetail}
				</Text>
			)}
		</Section>
	);
}

export const onSale = (row: Item) => row.price_list_rate > row.rate;

export function WasPrice({
	amount,
	fontSize,
}: { amount: number; fontSize: number }) {
	return (
		<span
			style={{
				marginLeft: 8,
				fontSize,
				fontWeight: t.regular,
				color: t.inkGray5,
				textDecoration: 'line-through',
			}}
		>
			{money(amount)}
		</span>
	);
}

function ItemRow({ row, imageBase }: { row: Item; imageBase: string }) {
	const thumb = imageUrl(imageBase, row.image, 'thumb');
	return (
		<Row style={{ borderBottom: `1px solid ${t.outlineGray1}` }}>
			<Column style={{ width: 64, verticalAlign: 'top' }}>
				{thumb ? (
					<Img
						src={thumb}
						width="52"
						height="64"
						alt=""
						style={{
							display: 'block',
							borderRadius: t.radiusThumb,
							backgroundColor: t.surfaceGray2,
							margin: '12px 0',
						}}
					/>
				) : (
					<PlaceholderTile
						name={row.item_name}
						width={52}
						height={64}
						margin="12px 0"
					/>
				)}
			</Column>
			<Column style={{ verticalAlign: 'top' }}>
				<Text style={{ ...s.value, lineHeight: '1.3', marginTop: 14 }}>
					{row.item_name}
				</Text>
				<Text style={{ ...s.caption, lineHeight: '1.4', marginTop: 3 }}>
					{row.variant}, qty <span style={num}>{row.qty}</span>
					{onSale(row) && (
						<span style={{ color: t.inkGreen6, fontWeight: t.medium }}>
							{' '}
							Sale
						</span>
					)}
				</Text>
			</Column>
			<Column align="right" style={{ verticalAlign: 'top', width: 110 }}>
				<Text style={{ ...s.value, ...num, marginTop: 14 }}>
					{money(row.qty * row.rate)}
				</Text>
				{onSale(row) && (
					<Text
						style={{
							...s.caption,
							...num,
							fontSize: 12,
							textDecoration: 'line-through',
							marginTop: 3,
						}}
					>
						{money(row.qty * row.price_list_rate)}
					</Text>
				)}
			</Column>
		</Row>
	);
}

export function ItemList({
	heading,
	items,
	imageBase,
}: { heading?: string; items: Item[]; imageBase: string }) {
	return (
		<>
			{heading && <Text style={s.sectionTitle}>{heading}</Text>}
			{items.map((row) => (
				<ItemRow key={row.item_code} row={row} imageBase={imageBase} />
			))}
		</>
	);
}

function ItemCard({ row, imageBase }: { row: Item; imageBase: string }) {
	const photo = imageUrl(imageBase, row.image, 'card');
	return (
		<>
			{photo ? (
				<Img
					src={photo}
					alt={row.item_name}
					width="272"
					height="240"
					style={{
						display: 'block',
						width: '100%',
						height: 240,
						objectFit: 'cover',
						objectPosition: '50% 25%',
						borderRadius: t.radiusThumb,
						backgroundColor: t.surfaceGray2,
					}}
				/>
			) : (
				<PlaceholderTile
					name={row.item_name}
					width="100%"
					height={240}
					fontSize={24}
				/>
			)}
			<Text style={{ ...s.value, marginTop: 12, lineHeight: '1.3' }}>
				{row.item_name}
			</Text>
			<Text style={{ ...s.caption, marginTop: 3 }}>
				{row.variant}
				{row.qty > 1 ? `, ${row.qty} pieces` : ''}
			</Text>
			<Text style={{ ...s.value, ...num, marginTop: 6 }}>
				{money(row.qty * row.rate)}
				{onSale(row) && (
					<WasPrice amount={row.qty * row.price_list_rate} fontSize={13} />
				)}
			</Text>
		</>
	);
}

export function ItemGrid({
	items,
	imageBase,
}: { items: Item[]; imageBase: string }) {
	const pairs: Item[][] = [];
	for (let index = 0; index < items.length; index += 2)
		pairs.push(items.slice(index, index + 2));
	return (
		<Section style={{ marginTop: 28 }}>
			{pairs.map((pair) => (
				<Row key={pair[0].item_code} style={{ marginBottom: 24 }}>
					{pair.map((row, position) => (
						<Column
							key={row.item_code}
							style={{
								width: '50%',
								verticalAlign: 'top',
								paddingLeft: position ? 8 : 0,
								paddingRight: position ? 0 : 8,
							}}
						>
							<ItemCard row={row} imageBase={imageBase} />
						</Column>
					))}
					{pair.length === 1 && <Column style={{ width: '50%' }} />}
				</Row>
			))}
		</Section>
	);
}

function Line({
	label,
	value,
	color = t.inkGray9,
}: { label: string; value: string; color?: string }) {
	return (
		<Row>
			<Column>
				<Text style={s.line}>{label}</Text>
			</Column>
			<Column align="right">
				<Text style={{ ...s.line, ...num, color }}>{value}</Text>
			</Column>
		</Row>
	);
}

function DiscountLine({ code, amount }: { code?: string; amount: number }) {
	return (
		<Line
			label={code ? `Discount (${code})` : 'Discount'}
			value={`−${money(amount)}`}
			color={t.inkGreen6}
		/>
	);
}

function TotalRow({ label, amount }: { label: string; amount: number }) {
	return (
		<Row>
			<Column>
				<Text style={title}>{label}</Text>
			</Column>
			<Column align="right">
				<Text style={s.amount}>{money(amount)}</Text>
			</Column>
		</Row>
	);
}

export function Totals({
	order,
	totalLabel = 'Total',
}: { order: Order; totalLabel?: string }) {
	const lookbook = useContext(LayoutContext) === 'lookbook';
	const { subtotal, grand, tax } = orderTotals(order);
	const lines = (
		<>
			<Line label="Subtotal" value={money(subtotal)} />
			{order.discount_amount > 0 && (
				<DiscountLine code={order.coupon_code} amount={order.discount_amount} />
			)}
			{order.charges.map((charge) => (
				<Line
					key={charge.description}
					label={charge.description}
					value={charge.amount ? money(charge.amount) : 'Free'}
				/>
			))}
			<Hr style={lookbook ? { ...s.hr, margin: '12px 0' } : s.hr} />
			{lookbook ? (
				<Row>
					<Column style={{ verticalAlign: 'bottom' }}>
						<Text style={s.caption}>Paid with {order.payment_method}</Text>
					</Column>
					<Column align="right">
						<Text
							style={{ ...s.amount, fontSize: 24, letterSpacing: '-0.015em' }}
						>
							{money(grand)}
						</Text>
					</Column>
				</Row>
			) : (
				<TotalRow label={totalLabel} amount={grand} />
			)}
			<Text
				style={{
					...s.muted,
					...num,
					textAlign: 'right',
					marginTop: lookbook ? 4 : 2,
				}}
			>
				Includes {money(tax)} {order.tax_label}
			</Text>
		</>
	);
	if (lookbook) {
		return (
			<Panel marginTop={8} padding="20px 24px 18px">
				{lines}
			</Panel>
		);
	}
	return (
		<>
			<Hr style={s.hr} />
			{lines}
		</>
	);
}

export function ReturnItems({
	order,
	returned,
	totalLabel,
	imageBase,
}: {
	order: Order;
	returned: Sample['return'];
	totalLabel: string;
	imageBase: string;
}) {
	const rows = returned.items.flatMap((line) => {
		const row = order.items.find((item) => item.item_code === line.item_code);
		return row ? [{ ...row, qty: line.qty }] : [];
	});
	const itemsTotal = rows.reduce((sum, row) => sum + row.qty * row.rate, 0);
	const discount =
		Math.round((itemsTotal - returned.refund_amount) * 100) / 100;
	return (
		<>
			<ItemList items={rows} imageBase={imageBase} />
			<Hr style={s.hr} />
			{discount > 0 && (
				<>
					<DiscountLine code={order.coupon_code} amount={discount} />
					<Hr style={s.hr} />
				</>
			)}
			<TotalRow label={totalLabel} amount={returned.refund_amount} />
		</>
	);
}

export function AddressBlock({
	label,
	address,
	emptyText,
	extraLines = [],
	bold = true,
}: {
	label: string;
	address?: Address | null;
	emptyText?: string;
	extraLines?: (string | null | undefined)[];
	bold?: boolean;
}) {
	if (!address && !emptyText) return null;
	const lines = [...(address?.lines ?? []), ...extraLines].filter(Boolean);
	return (
		<>
			<Text style={s.label}>{label}</Text>
			<Text style={s.address}>
				{!address && emptyText}
				{address && bold && <b style={s.strong}>{address.name}</b>}
				{address && !bold && address.name}
				{lines.map((line) => (
					<span key={line}>
						<br />
						{line}
					</span>
				))}
			</Text>
		</>
	);
}

export function BillingAddress({
	order,
	bold,
}: { order: Order; bold?: boolean }) {
	return (
		<Section style={{ marginTop: 16 }}>
			<AddressBlock
				label="Billing to"
				address={order.billing}
				emptyText="Same as shipping address"
				extraLines={[order.customer_tax_id && `GSTIN ${order.customer_tax_id}`]}
				bold={bold}
			/>
		</Section>
	);
}

export function FactBlock({
	label,
	title,
	detail,
}: { label: string; title: string; detail?: string }) {
	return (
		<AddressBlock
			label={label}
			address={{ name: title, lines: [] }}
			extraLines={[detail]}
		/>
	);
}

export function NoteBlock({
	label,
	body,
	first = true,
}: { label: string; body?: string; first?: boolean }) {
	if (!body) return null;
	return (
		<>
			<Text style={{ ...s.label, marginTop: first ? 0 : 16 }}>{label}</Text>
			<Text style={s.para}>{body}</Text>
		</>
	);
}

export function Footer({
	brand,
	closing,
	reason = `You're receiving this because you placed an order at ${brand.name}.`,
	links = brand.footer_links,
}: {
	brand: Brand;
	closing?: string;
	reason?: string;
	links?: { label: string; url: string }[];
}) {
	const classic = useContext(LayoutContext) === 'classic';
	return (
		<Section style={{ padding: classic ? `${closing ? 8 : 20}px 4px 0` : 0 }}>
			{closing && (
				<Text style={{ ...s.para, marginBottom: 16 }}>{closing}</Text>
			)}
			{links.length > 0 && (
				<Text style={{ ...s.muted, marginBottom: 8 }}>
					{links.map((link, index) => (
						<Link
							key={link.label}
							href={link.url}
							style={{
								color: t.inkGray7,
								textDecoration: 'underline',
								marginLeft: index ? 16 : 0,
							}}
						>
							{link.label}
						</Link>
					))}
				</Text>
			)}
			<Text style={{ ...s.muted, lineHeight: '1.5' }}>
				{brand.legal_name}, {brand.address}. GSTIN {brand.tax_id}.
				<br />
				{reason}
			</Text>
		</Section>
	);
}
