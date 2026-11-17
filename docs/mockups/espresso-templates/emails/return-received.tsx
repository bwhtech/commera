import { Column, Row, Text } from '@react-email/components';
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
import { type Sample, fill, money, t } from '../kit/data';

export default function ReturnReceived({
	brand,
	order,
	return: returned,
	copy,
	imageBase,
}: Sample) {
	const text = copy.return_received;
	const values = {
		first_name: order.customer_first_name,
		order_number: order.name,
		return_number: returned.name,
	};

	return (
		<EmailLayout
			layout="classic"
			preview={`Return ${returned.name} received. Expected refund ${money(
				returned.refund_amount,
			)}.`}
		>
			<Header brand={brand} layout="classic" meta={`Return ${returned.name}`} />

			<Card first>
				<Heading layout="classic">{fill(text.heading, values)}</Heading>
				<Intro layout="classic">{fill(text.intro, values)}</Intro>
				<Panel>
					<Text style={s.label}>Return number</Text>
					<Text style={{ ...s.amount, fontVariantNumeric: 'normal' }}>
						{returned.name}
					</Text>
					<Text style={{ ...s.address, marginTop: 6 }}>
						Requested on {returned.requested_on}, for order{' '}
						<span style={{ whiteSpace: 'nowrap' }}>{order.name}</span>.
					</Text>
				</Panel>
				{returned.next_steps.length > 0 && (
					<>
						<Text style={{ ...s.sectionTitle, marginTop: 24, marginBottom: 4 }}>
							How to send it back
						</Text>
						{returned.next_steps.map((step, index) => (
							<Row key={step} style={{ marginTop: 8 }}>
								<Column style={{ width: 24, verticalAlign: 'top' }}>
									<Text
										style={{
											...s.para,
											...s.num,
											color: t.inkGray9,
											fontWeight: t.semibold,
										}}
									>
										{index + 1}
									</Text>
								</Column>
								<Column style={{ verticalAlign: 'top' }}>
									<Text style={s.para}>{fill(step, values)}</Text>
								</Column>
							</Row>
						))}
					</>
				)}
				<Button href={returned.return_url}>{text.button}</Button>
			</Card>

			<Card>
				<Text style={s.sectionTitle}>Items you're returning</Text>
				<ReturnItems
					order={order}
					returned={returned}
					refundAmount={returned.refund_amount}
					totalLabel="Expected refund"
					imageBase={imageBase}
				/>
				<Text style={{ ...s.muted, marginTop: 10 }}>
					Back to {returned.refund_method}, {returned.refund_days} after the
					item reaches us.
				</Text>
			</Card>

			<Footer
				brand={brand}
				closing={fill(text.closing, values)}
				reason={`You're receiving this because you asked to return an item to ${brand.name}.`}
			/>
		</EmailLayout>
	);
}
