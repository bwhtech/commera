import { Section, Text } from '@react-email/components';
import {
	AddressBlock,
	AmountPanel,
	Button,
	Card,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	ItemList,
	ProgressSteps,
	s,
} from '../kit/components';
import { type Sample, fill, orderValues } from '../kit/data';

export default function ReadyForPickup({
	brand,
	order,
	steps,
	pickup,
	copy,
	imageBase,
}: Sample) {
	const text = copy.ready_for_pickup;
	const values = orderValues(order);

	return (
		<EmailLayout
			preview={`Order ${order.name} is ready at ${pickup.store_name}. Collect it by ${pickup.collect_by}.`}
		>
			<Header brand={brand} meta={`Order ${order.name}`} />

			<Card first>
				<Heading>{fill(text.heading, values)}</Heading>
				<Intro>{fill(text.intro, values)}</Intro>
				<ProgressSteps steps={steps} />
				<AmountPanel label="Collect by" amount={pickup.collect_by}>
					Bring your order number <b style={s.strong}>{order.name}</b> and a
					photo ID.
				</AmountPanel>
				<Button href={pickup.directions_url}>{text.button}</Button>
			</Card>

			<Card>
				<AddressBlock label="Pick up from" address={pickup.address} />
				{pickup.hours.length > 0 && (
					<Section style={{ marginTop: 16 }}>
						<Text style={s.label}>Opening hours</Text>
						<Text style={s.address}>
							{pickup.hours.map((line, index) => (
								<span key={line}>
									{index > 0 && <br />}
									{line}
								</span>
							))}
						</Text>
					</Section>
				)}
			</Card>

			<Card>
				<ItemList
					heading="To collect"
					items={order.items}
					imageBase={imageBase}
				/>
			</Card>

			<Footer brand={brand} closing={fill(text.closing, values)} />
		</EmailLayout>
	);
}
