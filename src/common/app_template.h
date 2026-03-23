/*****************************************************************************\
 *  src/common/app_template.h - application template configuration support
 *****************************************************************************
 *  This file is part of Metastack, a fork of Slurm.
 *
 *  Metastack is free software; you can redistribute it and/or modify it under
 *  the terms of the GNU General Public License as published by the Free
 *  Software Foundation; either version 2 of the License, or (at your option)
 *  any later version.
 *
 *  Metastack is distributed in the hope that it will be useful, but WITHOUT
 *  ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 *  FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 *  more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with Metastack; if not, write to the Free Software Foundation, Inc.,
 *  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
\*****************************************************************************/
#ifndef _APP_TEMPLATE_H
#define _APP_TEMPLATE_H

#include "slurm/slurm.h"

#ifdef __METASTACK_NEW_APP_TEMPLATE

#include "src/common/slurm_opt.h"

/*
 * Apply application template settings to the job options.
 *
 * Loads the app_template.conf configuration file, looks up the section
 * matching the application name specified by --app, and applies the
 * template's default settings:
 *   - Environment variables (env key) are always merged into the job
 *     environment.
 *   - Job parameters (partition, gres, ntasks, cpus_per_task, mem_per_cpu,
 *     time_limit) are applied only if not already explicitly set by the user.
 *
 * IN opt - pointer to the slurm_opt_t structure (must have opt->app set)
 *
 * Returns SLURM_SUCCESS on success, or SLURM_ERROR on failure.
 */
extern int app_template_apply(slurm_opt_t *opt);

#endif /* __METASTACK_NEW_APP_TEMPLATE */
#endif /* _APP_TEMPLATE_H */
