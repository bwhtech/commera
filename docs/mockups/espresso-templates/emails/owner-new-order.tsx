import { Column, Row, Section, Text } from '@react-email/components';
import {
	AddressBlock,
	Button,
	Card,
	EmailLayout,
	FactBlock,
	Footer,
	Header,
	Heading,
	Intro,
	NoteBlock,
	Totals,
	s,
} from '../kit/components';
import {
	type Item,
	type Sample,
	fill,
	money,
	orderTotals,
	t,
} from '../kit/data';

function CompactItem({ row }: { row: Item }) {
	return (
		<Row style={{ borderBottom: `1px solid ${t.outlineGray1}` }}>
			<Column style={{ verticalAlign: 'top', padding: '10px 0' }}>
				<Text
					style={{
						...s.para,
						color: t.inkGray9,
						fontWeight: t.medium,
						lineHeight: '1.35',
					}}
				>
					{row.item_name}
				</Text>
				<Text style={{ ...s.muted, marginTop: 2 }}>
					{row.variant}
					<br />
					{row.item_code}
				</Text>
			</Column>
			<Column
				align="right"
				style={{ verticalAlign: 'top', width: 120, padding: '10px 0' }}
			>
				<Text
					style={{
						...s.para,
						...s.num,
						color: t.inkGray9,
						fontWeight: t.medium,
						lineHeight: '1.35',
					}}
				>
					{money(row.qty * row.rate)}
				</Text>
				<Text style={{ ...s.muted, ...s.num, marginTop: 2 }}>
					{row.qty} × {money(row.rate)}
				</Text>
			</Column>
		</Row>
	);
}

export default function OwnerNewOrder({ brand, order, copy }: Sample) {
	const text = copy.owner_new_order;
	const { grand } = orderTotals(order);
	const values = {
		order_number: order.name,
		customer_name: order.customer_name,
		total: money(grand),
	};
	const dashboardUrl = `${brand.store_url}/commera/orders/${order.name}`;

	return (
		<EmailLayout
			layout="classic"
			preview={`${order.customer_name}, ${money(grand)}, ${
				order.payment_status
			}.`}
		>
			<Header
				brand={brand}
				layout="classic"
				meta={`${order.transaction_date}, ${order.transaction_time}`}
			/>

			<Card first>
				<Heading layout="classic">{fill(text.heading, values)}</Heading>
				<Intro layout="classic">{fill(text.intro, values)}</Intro>
				<Row style={{ marginTop: 20 }}>
					<Column style={s.half}>
						<FactBlock
							label="Customer"
							title={order.customer_name}
							detail={order.contact_mobile}
						/>
					</Column>
					<Column style={s.half}>
						<FactBlock
							label="Payment"
							title={order.payment_status}
							detail={order.payment_method}
						/>
					</Column>
				</Row>
				<Row style={{ marginTop: 16 }}>
					<Column style={s.half}>
						<FactBlock
							label="Delivery"
							title={order.delivery_method}
							detail={`Due ${order.delivery_window}`}
						/>
					</Column>
					<Column style={s.half}>
						<FactBlock
							label="Items"
							title={`${order.items.reduce(
								(sum, row) => sum + row.qty,
								0,
							)} pieces`}
							detail={`${order.items.length} lines`}
						/>
					</Column>
				</Row>
				<Button href={dashboardUrl}>{text.button}</Button>
			</Card>

			<Card>
				<Text style={s.sectionTitle}>Items</Text>
				{order.items.map((row) => (
					<CompactItem key={row.item_code} row={row} />
				))}
				<Totals order={order} layout="classic" />
			</Card>

			<Card>
				<AddressBlock
					label="Shipping to"
					address={order.shipping}
					extraLines={[order.contact_email, order.contact_mobile]}
				/>
				{(order.customer_note || order.gift_message) && (
					<Section style={{ marginTop: 16 }}>
						<NoteBlock label="Delivery note" body={order.customer_note} />
						<NoteBlock
							label="Gift message"
							body={order.gift_message}
							first={!order.customer_note}
						/>
					</Section>
				)}
			</Card>

			<Footer
				brand={brand}
				links={[
					{
						label: 'Notification settings',
						url: `${brand.store_url}/commera/settings/notifications`,
					},
				]}
				reason={`You're receiving this because you're an admin of ${brand.name}.`}
			/>
		</EmailLayout>
	);
}
