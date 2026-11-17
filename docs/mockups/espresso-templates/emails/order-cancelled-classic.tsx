import { Text } from '@react-email/components';
import {
	Button,
	Card,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	ItemRow,
	Panel,
	Totals,
	s,
} from '../kit/components';
import { type Sample, fill, money, orderTotals } from '../kit/data';

export default function OrderCancelledClassic({
	brand,
	order,
	cancellation,
	copy,
	imageBase,
}: Sample) {
	const text = copy.order_cancelled;
	const { grand } = orderTotals(order);
	const values = {
		first_name: order.customer_first_name,
		order_number: order.name,
		reason: cancellation.reason,
	};

	return (
		<EmailLayout
			layout="classic"
			preview={`Order ${order.name} is cancelled. ${money(
				grand,
			)} goes back to ${order.payment_method} in ${cancellation.refund_days}.`}
		>
			<Header brand={brand} layout="classic" meta={`Order ${order.name}`} />

			<Card first>
				<Heading layout="classic">{fill(text.heading, values)}</Heading>
				<Intro layout="classic">{fill(text.intro, values)}</Intro>
				<Panel>
					<Text style={s.label}>Your refund</Text>
					<Text style={s.amount}>{money(grand)}</Text>
					<Text style={{ ...s.address, marginTop: 6 }}>
						Back to <b style={s.strong}>{order.payment_method}</b> within{' '}
						{cancellation.refund_days}.
					</Text>
				</Panel>
				<Button href={order.order_url}>{text.button}</Button>
			</Card>

			<Card>
				<Text style={s.sectionTitle}>Cancelled items</Text>
				{order.items.map((row) => (
					<ItemRow key={row.item_code} row={row} imageBase={imageBase} />
				))}
				<Totals order={order} layout="classic" />
			</Card>

			<Footer
				brand={brand}
				closing={fill(text.closing, values)}
				reason={`You're receiving this because you placed an order at ${brand.name}.`}
			/>
		</EmailLayout>
	);
}
