import { Link, Text } from '@react-email/components';
import {
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
import { type Sample, fill, orderValues, t } from '../kit/data';

export default function Delivered({
	brand,
	order,
	steps,
	shipment,
	copy,
	imageBase,
}: Sample) {
	const text = copy.delivered;
	const values = orderValues(order);

	return (
		<EmailLayout
			preview={`Order ${order.name} was delivered on ${shipment.delivered_on}.`}
		>
			<Header brand={brand} meta={`Order ${order.name}`} />

			<Card first>
				<Heading>{fill(text.heading, values)}</Heading>
				<Intro>{fill(text.intro, values)}</Intro>
				<ProgressSteps steps={steps} />
				<Button href={order.order_url}>{text.button}</Button>
			</Card>

			<Card>
				<ItemList
					heading="What arrived"
					items={order.items}
					imageBase={imageBase}
				/>
			</Card>

			{shipment.return_by && (
				<Card>
					<Text style={s.sectionTitle}>How did it go?</Text>
					<Text style={s.para}>
						If something doesn't fit or isn't what you hoped, you can return it
						until <span style={s.num}>{shipment.return_by}</span>.
					</Text>
					<Text style={{ ...s.para, marginTop: 10 }}>
						<Link
							href={`${brand.store_url}/returns`}
							style={{
								color: t.inkGray9,
								fontWeight: t.medium,
								textDecoration: 'underline',
							}}
						>
							Start a return
						</Link>
					</Text>
				</Card>
			)}

			<Footer brand={brand} closing={fill(text.closing, values)} />
		</EmailLayout>
	);
}
