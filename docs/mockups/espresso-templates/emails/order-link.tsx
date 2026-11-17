import { Column, Row, Text } from '@react-email/components';
import {
	Button,
	Card,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	s,
} from '../kit/components';
import {
	type Sample,
	fill,
	money,
	orderTotals,
	orderValues,
} from '../kit/data';

export default function OrderLink({ brand, order, copy }: Sample) {
	const text = copy.order_link;
	const { grand } = orderTotals(order);
	const values = orderValues(order);

	return (
		<EmailLayout
			preview={`Your link to order ${order.name}, placed on ${order.transaction_date}.`}
		>
			<Header brand={brand} meta={`Order ${order.name}`} />

			<Card first>
				<Heading>{fill(text.heading, values)}</Heading>
				<Intro>{fill(text.intro, values)}</Intro>
				<Row style={{ marginTop: 22 }}>
					<Column
						style={{ width: '36%', verticalAlign: 'top', paddingRight: 12 }}
					>
						<Text style={s.label}>Order number</Text>
						<Text style={{ ...s.address, ...s.strong }}>{order.name}</Text>
					</Column>
					<Column
						style={{ width: '32%', verticalAlign: 'top', paddingRight: 12 }}
					>
						<Text style={s.label}>Placed on</Text>
						<Text style={{ ...s.address, ...s.strong, ...s.num }}>
							{order.transaction_date}
						</Text>
					</Column>
					<Column style={{ width: '32%', verticalAlign: 'top' }}>
						<Text style={s.label}>Total</Text>
						<Text style={{ ...s.address, ...s.strong, ...s.num }}>
							{money(grand)}
						</Text>
					</Column>
				</Row>
				<Button href={order.order_url}>{text.button}</Button>
				<Text style={{ ...s.muted, marginTop: 20, lineHeight: '1.5' }}>
					This link is private. Anyone who has it can see your order, so please
					don't forward this email.
				</Text>
			</Card>

			<Footer
				brand={brand}
				closing={fill(text.closing, values)}
				links={[]}
				reason={`You're receiving this because someone asked for the link to this order at ${brand.name}.`}
			/>
		</EmailLayout>
	);
}
