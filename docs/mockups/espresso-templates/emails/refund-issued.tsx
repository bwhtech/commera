import { Text } from '@react-email/components';
import {
	Button,
	Card,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	Panel,
	ReturnItems,
	s,
} from '../kit/components';
import { type Sample, fill, money } from '../kit/data';

export default function RefundIssued({
	brand,
	order,
	return: returned,
	copy,
	imageBase,
}: Sample) {
	const text = copy.refund_issued;
	const values = {
		first_name: order.customer_first_name,
		order_number: order.name,
		return_number: returned.name,
	};

	return (
		<EmailLayout
			layout="classic"
			preview={`${money(returned.refund_amount)} refunded to ${
				returned.refund_method
			}. Allow ${returned.refund_days}.`}
		>
			<Header brand={brand} layout="classic" meta={`Order ${order.name}`} />

			<Card first>
				<Heading layout="classic">{fill(text.heading, values)}</Heading>
				<Intro layout="classic">{fill(text.intro, values)}</Intro>
				<Panel>
					<Text style={s.label}>Refunded on {returned.refunded_on}</Text>
					<Text style={s.amount}>{money(returned.refund_amount)}</Text>
					<Text style={{ ...s.address, marginTop: 6 }}>
						Back to <b style={s.strong}>{returned.refund_method}</b>. Allow{' '}
						{returned.refund_days} for it to show.
					</Text>
				</Panel>
				<Button href={order.order_url}>{text.button}</Button>
			</Card>

			<Card>
				<Text style={s.sectionTitle}>Refunded items</Text>
				<Text style={{ ...s.muted, marginTop: -4 }}>
					Return {returned.name}
				</Text>
				<ReturnItems
					order={order}
					returned={returned}
					refundAmount={returned.refund_amount}
					totalLabel="Refund total"
					imageBase={imageBase}
				/>
			</Card>

			<Footer
				brand={brand}
				closing={fill(text.closing, values)}
				reason={`You're receiving this because you returned an item to ${brand.name}.`}
			/>
		</EmailLayout>
	);
}
