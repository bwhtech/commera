import { Section, Text } from '@react-email/components';
import {
	Card,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	s,
} from '../kit/components';
import { type Sample, fill, t } from '../kit/data';

export default function SignInCode({ brand, sign_in, copy }: Sample) {
	const text = copy.sign_in_code;
	const values = { store_name: brand.name };

	return (
		<EmailLayout
			layout="classic"
			preview={`Your ${brand.name} sign-in code is ${sign_in.code}. It expires in ${sign_in.expires_in_minutes} minutes.`}
		>
			<Header brand={brand} layout="classic" />

			<Card first>
				<Heading layout="classic">{fill(text.heading, values)}</Heading>
				<Intro layout="classic">{fill(text.intro, values)}</Intro>
				<Section
					style={{
						backgroundColor: t.surfaceGray2,
						borderRadius: t.radiusCard,
						padding: '20px 16px',
						marginTop: 22,
					}}
				>
					<Text
						style={{
							...s.num,
							margin: 0,
							fontFamily: t.font,
							fontSize: 36,
							lineHeight: '1.1',
							fontWeight: t.semibold,
							letterSpacing: '0.16em',
							paddingLeft: '0.16em',
							color: t.inkGray9,
							textAlign: 'center',
						}}
					>
						{sign_in.code}
					</Text>
				</Section>
				<Text style={{ ...s.para, marginTop: 16 }}>
					The code expires in {sign_in.expires_in_minutes} minutes.
				</Text>
				<Text style={{ ...s.para, marginTop: 4 }}>
					{fill(text.closing, values)}
				</Text>
			</Card>

			<Footer
				brand={brand}
				links={[]}
				reason={`You're receiving this because someone asked to sign in to ${brand.name} with this email address.`}
			/>
		</EmailLayout>
	);
}
