import { Text } from '@react-email/components';
import {
	AmountPanel,
	Button,
	Card,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	ReturnItems,
	s,
} from '../kit/components';
import { type Sample, fill, money, orderValues } from '../kit/data';

export default function RefundIssued({
	brand,
	order,
	return: returned,
	copy,
	imageBase,
}: Sample) {
	const text = copy.refund_issued;
	const values = { ...orderValues(order), return_number: returned.name };

	return (
		<EmailLayout
			preview={`${money(returned.refund_amount)} refunded to ${
				returned.refund_method
			}. Allow ${returned.refund_days}.`}
		>
			<Header brand={brand} meta={`Order ${order.name}`} />

			<Card first>
				<Heading>{fill(text.heading, values)}</Heading>
				<Intro>{fill(text.intro, values)}</Intro>
				<AmountPanel
					label={`Refunded on ${returned.refunded_on}`}
					amount={money(returned.refund_amount)}
				>
					Back to <b style={s.strong}>{returned.refund_method}</b>. Allow{' '}
					{returned.refund_days} for it to show.
				</AmountPanel>
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
