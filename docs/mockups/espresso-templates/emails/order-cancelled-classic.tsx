import { Section, Text } from "@react-email/components";
import { Button, Card, EmailLayout, Footer, Header, Heading, Intro, ItemRow, Totals, s } from "../kit/components";
import { type Sample, fill, money, orderTotals, t } from "../kit/data";

export default function OrderCancelledClassic({ brand, order, cancellation, copy, imageBase }: Sample) {
	const text = copy.order_cancelled;
	const { grand } = orderTotals(order);
	const values = { first_name: order.customer_first_name, order_number: order.name, reason: cancellation.reason };

	return (
		<EmailLayout
			layout="classic"
			preview={`Order ${order.name} is cancelled. ${money(grand)} goes back to ${order.payment_method} in ${cancellation.refund_days}.`}
		>
			<Header brand={brand} layout="classic" meta={`Order ${order.name}`} />

			<Card first>
				<Heading layout="classic">{fill(text.heading, values)}</Heading>
				<Intro layout="classic">{fill(text.intro, values)}</Intro>
				<Section style={{ backgroundColor: t.surfaceGray2, borderRadius: t.radiusCard, padding: "16px 20px", marginTop: 22 }}>
					<Text style={s.label}>Your refund</Text>
					<Text style={{ ...s.num, margin: 0, fontFamily: t.font, fontSize: 20, fontWeight: t.semibold, letterSpacing: "-0.01em", color: t.inkGray9 }}>
						{money(grand)}
					</Text>
					<Text style={{ ...s.address, marginTop: 6 }}>
						Back to <b style={s.strong}>{order.payment_method}</b> within {cancellation.refund_days}.
					</Text>
				</Section>
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
