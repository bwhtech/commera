import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { Column, Row, Text } from '@react-email/components';
import { render } from '@react-email/render';
import type { ComponentType } from 'react';
import {
	Button,
	Card,
	EmailLayout,
	Heading,
	Intro,
	ProgressSteps,
} from './kit/components';
import { type Step, t } from './kit/data';
import {
	AmazonStepper,
	AppleStepper,
	FlipkartStepper,
	HimsStepper,
	NikeStepper,
	ShopifyStepper,
	type StepperProps,
	type StepperStep,
} from './kit/stepper_options';

const CHROMIUM =
	'/home/frappe/.agent-browser/browsers/chrome-157.0.8103.78/chrome';
const outDir = resolve(import.meta.dirname, 'out/steppers');
mkdirSync(outDir, { recursive: true });

type State = {
	key: string;
	heading: string;
	intro: string;
	button: string;
	stepper: StepperProps;
	currentHints: string[];
};

const titles = ['Confirmed', 'Packed', 'Shipped', 'Delivered'];

function steps(
	dates: (string | undefined)[],
	doneCount: number,
): StepperStep[] {
	return titles.map((title, index) => ({
		title,
		date: dates[index],
		done: index < doneCount,
	}));
}

const states: State[] = [
	{
		key: 'confirmed',
		heading: 'Thanks, Aisha. Your order is in.',
		intro:
			"We've received your order and our team is getting it ready. We'll email you again with tracking details as soon as it ships.",
		button: 'View your order',
		stepper: {
			steps: steps(['28 Sep', undefined, undefined, '2 to 4 Oct'], 1),
			status: { label: 'Arriving', date: '2 to 4 Oct' },
		},
		currentHints: ['28 Sep', 'Within a day', 'Tracking by email', '2 to 4 Oct'],
	},
	{
		key: 'shipped',
		heading: 'Aisha, your order is on its way.',
		intro:
			'Your parcel has left our studio. You can follow it with the tracking link below.',
		button: 'Track your parcel',
		stepper: {
			steps: steps(['28 Sep', '29 Sep', '30 Sep', '3 Oct'], 3),
			status: {
				label: 'Arriving',
				date: '3 Oct',
				detail: 'Shipped with Delhivery',
			},
		},
		currentHints: ['28 Sep', '29 Sep', 'Delhivery', 'Arriving 3 Oct'],
	},
	{
		key: 'delivered',
		heading: 'Aisha, your order has arrived.',
		intro:
			'Delhivery left your parcel at the address you gave us. We hope you love it.',
		button: 'View your order',
		stepper: {
			steps: steps(['28 Sep', '29 Sep', '30 Sep', '3 Oct'], 4),
			status: { label: 'Delivered', date: '3 Oct' },
		},
		currentHints: ['28 Sep', '29 Sep', '30 Sep', '3 Oct'],
	},
];

function CurrentStepper({
	steps: stepperSteps,
	hints,
}: StepperProps & { hints: string[] }) {
	const kitSteps: Step[] = stepperSteps.map((step, index) => ({
		title: step.title,
		hint: hints[index],
		done: step.done,
	}));
	return <ProgressSteps steps={kitSteps} layout="classic" />;
}

type Option = {
	id: string;
	Stepper: ComponentType<StepperProps & { hints: string[] }>;
};

const options: Option[] = [
	{ id: 'current', Stepper: CurrentStepper },
	{ id: 'amazon', Stepper: AmazonStepper },
	{ id: 'apple', Stepper: AppleStepper },
	{ id: 'shopify', Stepper: ShopifyStepper },
	{ id: 'flipkart', Stepper: FlipkartStepper },
	{ id: 'hims', Stepper: HimsStepper },
	{ id: 'nike', Stepper: NikeStepper },
];

function StepperCard({ option, state }: { option: Option; state: State }) {
	return (
		<EmailLayout layout="classic" preview={state.heading}>
			<Card first>
				<Heading layout="classic">{state.heading}</Heading>
				<Intro layout="classic">{state.intro}</Intro>
				<option.Stepper {...state.stepper} hints={state.currentHints} />
				<Button href="https://espresso.example/orders/SO-2026-00412">
					{state.button}
				</Button>
			</Card>
		</EmailLayout>
	);
}

const A4_WIDTH = 794;

function PdfHero({ option, state }: { option: Option; state: State }) {
	return (
		<html lang="en">
			<head>
				<meta charSet="utf-8" />
				<link href={t.fontStylesheet} rel="stylesheet" />
			</head>
			<body
				style={{
					margin: 0,
					backgroundColor: t.surfaceBase,
					fontFamily: t.font,
					width: A4_WIDTH,
					padding: '45px 53px',
					boxSizing: 'border-box',
				}}
			>
				<div
					style={{
						backgroundColor: t.surfaceGray2,
						borderRadius: t.radiusCard,
						padding: '24px 28px 20px',
					}}
				>
					<Row>
						<Column style={{ verticalAlign: 'bottom' }}>
							<Text
								style={{
									margin: 0,
									fontFamily: t.font,
									fontSize: 27,
									fontWeight: t.semibold,
									letterSpacing: '-0.02em',
									lineHeight: '1.12',
									color: t.inkGray9,
								}}
							>
								{state.heading}
							</Text>
							<Text
								style={{
									margin: '8px 0 0',
									fontFamily: t.font,
									fontSize: 13,
									lineHeight: '1.55',
									color: t.inkGray7,
									maxWidth: 420,
								}}
							>
								{state.intro}
							</Text>
						</Column>
						<Column
							align="right"
							style={{
								verticalAlign: 'bottom',
								width: 190,
								whiteSpace: 'nowrap',
							}}
						>
							<Text
								style={{
									margin: '0 0 6px',
									fontFamily: t.font,
									fontSize: 12,
									color: t.inkGray5,
								}}
							>
								Order number
							</Text>
							<Text
								style={{
									margin: 0,
									fontFamily: t.font,
									fontSize: 22,
									fontWeight: t.semibold,
									color: t.inkGray9,
								}}
							>
								SO-26-00482
							</Text>
						</Column>
					</Row>
					<div
						style={{ borderTop: `1px solid ${t.outlineGray2}`, marginTop: 18 }}
					>
						<option.Stepper
							{...state.stepper}
							hints={state.currentHints}
							onGray
						/>
					</div>
				</div>
			</body>
		</html>
	);
}

function shoot(htmlFile: string, pngFile: string, width: number) {
	execFileSync(
		CHROMIUM,
		[
			'--headless=new',
			'--disable-gpu',
			'--hide-scrollbars',
			'--allow-file-access-from-files',
			'--force-device-scale-factor=2',
			`--window-size=${width},1400`,
			'--virtual-time-budget=8000',
			`--screenshot=${pngFile}`,
			pathToFileURL(htmlFile).href,
		],
		{ stdio: 'ignore' },
	);
}

for (const option of options) {
	for (const state of states) {
		const name = `${option.id}-${state.key}`;
		const htmlFile = resolve(outDir, `${name}.html`);
		writeFileSync(
			htmlFile,
			await render(<StepperCard option={option} state={state} />),
		);
		shoot(htmlFile, resolve(outDir, `${name}-desktop.png`), 720);
		console.log(name);
	}
	if (option.id === 'current') continue;
	const pdfFile = resolve(outDir, `${option.id}-pdf.html`);
	writeFileSync(
		pdfFile,
		await render(<PdfHero option={option} state={states[0]} />),
	);
	shoot(pdfFile, resolve(outDir, `${option.id}-pdf.png`), A4_WIDTH);
}
