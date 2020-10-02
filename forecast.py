import pickle
import random

import numpy as np
import pandas as pd

from scipy import stats
from pprint import pprint
from functools import partial
from collections import defaultdict


N_SCENARIOS = 40000      # How many Monte Carlo simulations to run?

CREDIBLE_INTERVAL = 0.8  # 80% chance of donation falling within range, conditional on giving
ABSOLUTE_ERROR = 152250  # This is the width of the 80% normal interval in $ that we apply to every scenario (e.g., for uncertainty around the budget) (can be set to $0 to ignore)
# TODO: Should we jitter the chance of giving as well, to account for correlated errors / make the interval wider?

SCENARIO_RANGES = [1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99]  # Generate printed output for these percentiles
VERBOSE = False                                                       # Change this to True for scenario-specific outputs

SAVE = True   # Set to False to not save (overwrite) any model outputs
PATH = ""     # Use this to define a custom path for the saved model outputs


def parse_currency(currency):
    if currency == ' $ -   ':
        return 0
    elif isinstance(currency, str):
        currency = currency.replace('$', '').replace(' ', '').replace(',', '')
        return float(currency)
    else:
        return 0


def print_money(money):
    if money >= 0:
        return '${:,.2f}'.format(money)
    else:
        return '-${:,.2f}'.format(-money)


# Either round to nearest hundred if <1000 or nearest thousand if >= 1000
def round_to_nearest(num):
    n_digits = len(str(num))
    n_digits = n_digits - 1
    if n_digits > 3:
        n_digits = 3
    return np.round(num, -n_digits)


def parse_percent(percent):
    if isinstance(percent, str):
        return float(percent.replace('%', '')) / 100
    else:
        return 0


def normal_sample(low, high, interval):
    if (low > high) or (high < low):
        raise ValueError
    if low == high:
        return low
    else:
        mu = (high + low) / 2
        cdf_value = 0.5 + 0.5 * interval
        normed_sigma = stats.norm.ppf(cdf_value)
        sigma = (high - mu) / normed_sigma
        return np.random.normal(mu, sigma)


def lognormal_sample(low, high, interval):
    if (low > high) or (high < low):
        raise ValueError
    if low == high:
        return low
    else:
        log_low = np.log(low)
        log_high = np.log(high)
        mu = (log_high + log_low) / 2
        cdf_value = 0.5 + 0.5 * interval
        normed_sigma = stats.norm.ppf(cdf_value)
        sigma = (log_high - mu) / normed_sigma
        return np.random.lognormal(mu, sigma)


raw_data = pd.read_csv('forecast.csv')
raw_data = raw_data[raw_data['Donor'] != 'Current Donors'][raw_data['Donor'] != 'Possible Donors']
raw_data = raw_data.drop([' 2018 Gift Amount ',
                          ' 2019 Gift Amount ',
                          ' 2020 Gift Amount ',
                          ' 2021 Gift Amount '], axis=1)
fundraising_data = {}
for index, row in raw_data.iterrows():
    donor = row['Donor']
    if donor and isinstance(donor, str):
        y2020_low = parse_currency(row[' 2020 Gift Potential - Low '])
        y2020_high = parse_currency(row[' 2020 Gift Potential - High '])
        y2020_prob = parse_percent(row['2020 Likelihood of Gift'])
        y2021_low = parse_currency(row[' 2021 Gift Potential - Low '])
        y2021_high = parse_currency(row[' 2021 Gift Potential - High '])
        y2021_prob = parse_percent(row['2021 Likelihood of Gift'])

        fundraising_data[donor] = {'2020': {'low': y2020_low,
                                            'high': y2020_high,
                                            'prob': y2020_prob},
                                   '2021': {'low': y2021_low,
                                            'high': y2021_high,
                                            'prob': y2021_prob}}

y2020_all_scenario_totals = []
y2021_all_scenario_totals = []
y2020_fundraising_totals = defaultdict(partial(np.array, 0))
y2021_fundraising_totals = defaultdict(partial(np.array, 0))
joint_fundraising_totals = defaultdict(partial(np.array, 0))
absolute_errors = []

for s in range(N_SCENARIOS):
    if s % 100 == 0:
        if VERBOSE:
            print('-')
            print('### SCENARIO {} ###'.format(s + 1))
        else:
            print('... Completed {}/{}'.format(s + 1, N_SCENARIOS))

    y2020_donations = []
    y2021_donations = []

    for donor, donation in fundraising_data.items():
        if random.random() <= donation['2020']['prob']:
            y2020_donation = lognormal_sample(low=donation['2020']['low'],
                                              high=donation['2020']['high'],
                                              interval=CREDIBLE_INTERVAL)
        else:
            y2020_donation = 0

        if random.random() <= donation['2021']['prob']:
            y2021_donation = lognormal_sample(low=donation['2021']['low'],
                                              high=donation['2021']['high'],
                                              interval=CREDIBLE_INTERVAL)
        else:
            y2021_donation = 0

        y2020_donation = round_to_nearest(y2020_donation)
        y2021_donation = round_to_nearest(y2021_donation)

        if s % 100 == 0 and VERBOSE:
            print('{} gives {} in 2020 and {} in 2021'.format(donor,
                                                              print_money(y2020_donation),
                                                              print_money(y2021_donation)))
        y2020_donations.append(y2020_donation)
        y2021_donations.append(y2021_donation)
        y2020_fundraising_totals[donor] = np.append(y2020_fundraising_totals[donor], y2020_donation)
        y2021_fundraising_totals[donor] = np.append(y2021_fundraising_totals[donor], y2021_donation)
        joint_fundraising_totals[donor] = np.append(joint_fundraising_totals[donor], y2020_donation + y2021_donation)

    y2020_total_raised = sum(y2020_donations)
    if ABSOLUTE_ERROR > 0:
        scenario_absolute_error = normal_sample(low=0.1,
                                                high=ABSOLUTE_ERROR/2.0,
                                                interval=CREDIBLE_INTERVAL)
        if random.random() <= 0.5:
            scenario_absolute_error = -scenario_absolute_error
    else:
        scenario_absolute_error = 0

    y2021_total_raised = sum(y2021_donations) + scenario_absolute_error

    if s % 100 == 0 and VERBOSE:
        print('ABSOLUTE ERROR TERM: {}'.format(print_money(scenario_absolute_error)))
        print('TOTAL RAISED IN 2020: {}'.format(print_money(y2020_total_raised)))
        print('TOTAL RAISED IN 2021: {}'.format(print_money(y2021_total_raised)))

    y2020_all_scenario_totals.append(y2020_total_raised)
    y2021_all_scenario_totals.append(y2021_total_raised)
    absolute_errors.append(scenario_absolute_error)

if VERBOSE:
    print('-')
    print('-')
    print('-')


joint_scenarios = np.array(y2020_all_scenario_totals) + np.array(y2021_all_scenario_totals)
y2020_percentiles = np.percentile(y2020_all_scenario_totals, SCENARIO_RANGES)
y2021_percentiles = np.percentile(y2021_all_scenario_totals, SCENARIO_RANGES)
joint_percentiles = np.percentile(joint_scenarios, SCENARIO_RANGES)

print('SCENARIO 2020 -- {}'.format(' -- '.join(['{}%: {}'.format(s, print_money(y2020_percentiles[i])) for i, s in enumerate(SCENARIO_RANGES)])))
print('SCENARIO 2021 -- {}'.format(' -- '.join(['{}%: {}'.format(s, print_money(y2021_percentiles[i])) for i, s in enumerate(SCENARIO_RANGES)])))
print('SCENARIO -- {}'.format(' -- '.join(['{}%: {}'.format(s, print_money(joint_percentiles[i])) for i, s in enumerate(SCENARIO_RANGES)])))

if SAVE:
    print('... Saving 1/8')
    pickle.dump(fundraising_data, open('{}fundraising_data.p'.format(PATH), 'wb'))
    print('... Saving 2/8')
    pickle.dump(y2020_fundraising_totals, open('{}y2020_fundraising_totals.p'.format(PATH), 'wb'))
    print('... Saving 3/8')
    pickle.dump(y2021_fundraising_totals, open('{}y2021_fundraising_totals.p'.format(PATH), 'wb'))
    print('... Saving 4/8')
    pickle.dump(joint_fundraising_totals, open('{}joint_fundraising_totals.p'.format(PATH), 'wb'))
    print('... Saving 5/8')
    pickle.dump(y2020_all_scenario_totals, open('{}y2020_all_scenario_totals.p'.format(PATH), 'wb'))
    print('... Saving 6/8')
    pickle.dump(y2021_all_scenario_totals, open('{}y2021_all_scenario_totals.p'.format(PATH), 'wb'))
    print('... Saving 7/8')
    pickle.dump(joint_scenarios, open('{}joint_scenarios.p'.format(PATH), 'wb'))
    print('... Saving 8/8')
    pickle.dump(absolute_errors, open('{}absolute_errors.p'.format(PATH), 'wb'))

