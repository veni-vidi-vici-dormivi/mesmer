"""
mesmer.create_emulations.create_emus_gt
===================
Functions to create global trend emulations with MESMER.


Functions:
    create_emus_gt()

"""

import os

import joblib
import numpy as np


def create_emus_gt(params_gt, preds_gt, cfg, concat_h_f=False, save_emus=True):
    """Create global trend (emissions + volcanoes) emulations for specified ensemble type and method.

    Args:
    - params_gt (dict):
        ['targ'] (emulated variable, str)
        ['esm'] (Earth System Model, str)
        ['ens_type'] (type of ensemble which is emulated, str)
        ['method'] (applied method, str)
        ['preds'] (predictors, list of strs)
        ['scenarios'] (scenarios which are used for training, list of strs)
        ['time'] (1d array of years, np.ndarray)
        [xx] (additional keys depend on employed method and are listed in train_gt_T_ens_type_method() function)
    - preds_gt (dict): nested dictionary of predictors for global trend with keys
        [pred][scen] with 1d/2d arrays (time)/(run,time)
    - cfg (module): config file containnig metadata
    - concat_h_f (bool,optional): determines if historical and future time period is concatenated into a single
                                    emulation or not, default = False (must be set to false if no historical data provided)
    - save_emus (bool,optional): determines if emulation is saved or not, default = True

    Returns:
    - emus_gt (dict): global trend emulations dictionary with keys
        [scen] (1d array of global trend emulation time series)

    General remarks:
    - Assumption: - if no preds_gt needed, pass time as predictor instead to know which scenarios to emulate

    """

    # specify necessary variables from config file
    dir_mesmer_emus = cfg.dir_mesmer_emus

    # derive necessary scenario names
    pred_names = list(preds_gt.keys())
    scenarios_emus = list(preds_gt[pred_names[0]].keys())

    scens_out_f = list(map(lambda x: x.replace("h-", ""), scenarios_emus))
    # does nothing in case 'h-' not actually included

    if concat_h_f:
        scens_out = scenarios_emus
    else:
        if "h-" in scenarios_emus[0]:
            scens_out = ["hist"] + scens_out_f
        else:
            scens_out = scens_out_f

    # initialize global trend emulations dictionary with scenarios as keys
    emus_gt = {}

    # apply the chosen method
    if "LOWESS" in params_gt["method"]:
        if concat_h_f:
            for scen_out, scen_out_f in zip(scens_out, scens_out_f):
                emus_gt[scen_out] = np.concatenate(
                    [params_gt["hist"], params_gt[scen_out_f]]
                )
        else:
            for scen_out in scens_out:
                emus_gt[scen_out] = params_gt[scen_out]
    else:
        print("No alternative method is currently implemented.")

    # save the global trend emulation if requested
    if save_emus:
        dir_mesmer_emus_gt = dir_mesmer_emus + "global/global_trend/"
        # check if folder to save params in exists, if not: make it
        if not os.path.exists(dir_mesmer_emus_gt):
            os.makedirs(dir_mesmer_emus_gt)
            print("created dir:", dir_mesmer_emus_gt)
        filename_parts = [
            "emus_gt",
            params_gt["ens_type"],
            params_gt["method"],
            *params_gt["preds"],
            params_gt["targ"],
            params_gt["esm"],
            *scens_out,
        ]
        filename_emus_gt = dir_mesmer_emus_gt + "_".join(filename_parts) + ".pkl"
        joblib.dump(emus_gt, filename_emus_gt)

    return emus_gt