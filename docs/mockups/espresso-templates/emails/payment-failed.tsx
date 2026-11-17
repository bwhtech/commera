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

export default function PaymentFailed({
	brand,
	order,
	payment_failure,
	copy,
	imageBase,
}: Sample) {
	const text = copy.payment_failed;
	const { grand } = orderTotals(order);
	const values = {
		first_name: order.customer_first_name,
		order_number: order.name,
		hold_hours: String(payment_failure.hold_hours),
	};

	return (
		<EmailLayout
			layout="classic"
			preview={`Payment for order ${order.name} didn't go through. We're holding it until ${payment_failure.held_until}.`}
		>
			<Header brand={brand} layout="classic" meta={`Order ${order.name}`} />

			<Card first>
				<Heading layout="classic">{fill(text.heading, values)}</Heading>
				<Intro layout="classic">{fill(text.intro, values)}</Intro>
				<Panel>
					<Text style={s.label}>To pay</Text>
					<Text style={s.amount}>{money(grand)}</Text>
					<Text style={{ ...s.address, marginTop: 6 }}>
						Held until <b style={s.strong}>{payment_failure.held_until}</b>.
						Last tried with {payment_failure.attempted_method}.
					</Text>
				</Panel>
				<Button href={payment_failure.payment_url}>{text.button}</Button>
			</Card>

			<Card>
				<Text style={s.sectionTitle}>Order summary</Text>
				{order.items.map((row) => (
					<ItemRow key={row.item_code} row={row} imageBase={imageBase} />
				))}
				<Totals order={order} layout="classic" totalLabel="To pay" />
			</Card>

			<Footer
				brand={brand}
				closing={fill(text.closing, values)}
				reason={`You're receiving this because you placed an order at ${brand.name}.`}
			/>
		</EmailLayout>
	);
}
